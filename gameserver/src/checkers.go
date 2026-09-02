package main

import (
	"bytes"
	"context"
	"database/sql"
	"math/rand"
	"net"
	"sort"
	"strings"
	"sync"
	"time"

	"game/db"
	"game/log"

	"github.com/uptrace/bun"
)

const flagLen = 32

const (
	OK       = 101
	DOWN     = 104
	ERROR    = 110
	KILLED   = -1
	CRITICAL = 1337
	// NOT_CHECKED marks a check that never ran: there was nothing to verify,
	// which is not the same as a check that ran and passed. It counts as up
	// for the SLA, but the scoreboard draws it grey instead of green.
	NOT_CHECKED = 100
)

const (
	CHECK_SLA = "CHECK_SLA"
	PUT_FLAG  = "PUT_FLAG"
	GET_FLAG  = "GET_FLAG"
)

var randSrc *rand.Rand
var randLock sync.Mutex

func initRand() {
	randSrc = rand.New(rand.NewSource(time.Now().UnixNano()))
}

func genFlag() string {
	letters := "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
	randLock.Lock()
	defer randLock.Unlock()
	var flag string
	for range flagLen - 1 {
		index := randSrc.Intn(len(letters))
		flag += string(letters[index])
	}
	return flag + "="
}

func randomOffset(window time.Duration) time.Duration {
	if window <= 0 {
		return 0
	}
	randLock.Lock()
	defer randLock.Unlock()
	return time.Duration(randSrc.Int63n(int64(window)))
}

func genCheckFlag(team string, service string, round uint) string {
	var ctx context.Context = context.Background()
	for {
		flag := genFlag()
		_, err := conn.NewInsert().Model(&db.Flag{
			ID:      flag,
			Team:    team,
			Round:   round,
			Service: service,
		}).Exec(ctx)
		if err != nil {
			if strings.Contains(strings.ToLower(err.Error()), "duplicate") {
				log.Debugf("DUPLICATE FLAG %v -> %+v", flag, team)
			} else {
				log.Criticalf("Error inserting flag %v:%v on %v: %v", team, flag, service, err)
				return flag
			}
		} else {
			log.Debugf("NEW FLAG %v -> %+v", flag, team)
			return flag
		}
	}
}

func calcRoundStartTime(round uint) time.Time {
	return gs.StartTime().Add(time.Duration(int64(gs.RoundLen()) * int64(round)))
}

func remainingTimeFromRound(round uint) time.Duration {
	return time.Until(calcRoundStartTime(round))
}

func waitForRound(round uint) {
	for {
		timeToWait := time.Until(calcRoundStartTime(round))
		if timeToWait <= 0 {
			return
		}
		// Sleep in slices: an admin can move the start time (pause/resume) while
		// we are waiting and we must notice.
		if timeToWait > time.Second {
			timeToWait = time.Second
		}
		time.Sleep(timeToWait)
	}
}

func waitForGraceTime() {
	timeToWait := time.Until(gs.StartTime().Add(-gs.GraceDuration()))
	if timeToWait > 0 {
		time.Sleep(timeToWait)
	}
}

// waitWhilePaused blocks while the organizers keep the game paused and shifts
// the game clock forward by the paused duration on resume, so that the round
// numbering stays coherent with the wall clock.
func waitWhilePaused() {
	if !gs.Settings().GamePaused {
		return
	}
	pausedAt := time.Now()
	log.Warningf("Game paused by the organizers")
	for gs.Settings().GamePaused {
		time.Sleep(time.Second)
	}
	elapsed := time.Since(pausedAt)
	shiftGameClock(elapsed)
	log.Warningf("Game resumed, clock shifted by %v", elapsed.Truncate(time.Second))
}

func shiftGameClock(delta time.Duration) {
	newStart := gs.StartTime().Add(delta)
	db.SetStartTime(newStart)
	if end := gs.EndTime(); end != nil {
		newEnd := end.Add(delta)
		writeSetting(setEndTime, newEnd.Format(time.RFC3339))
	}
	if freeze := gs.Settings().ScoreboardFreezeAt; freeze != nil {
		newFreeze := freeze.Add(delta)
		writeSetting(setFreezeAt, newFreeze.Format(time.RFC3339))
	}
	ReloadState()
	invalidateAllCaches()
}

// calcSLA returns the ratio of rounds the service was fully up.
//
// It takes the database handle explicitly because it is called from inside the
// transaction that just inserted the status of the current round: using the
// pool instead would not see that row and the SLA would lag one round behind.
func calcSLA(dbc bun.IDB, ctx context.Context, team string, service string) (sla float64, totSla uint, upSla uint, err error) {
	totQuery := dbc.NewSelect().Model((*db.StatusHistory)(nil)).ColumnExpr("count(id)").Where("team = ? and service = ? and put_flag_status != ? and get_flag_status != ? and check_status != ?", team, service, CRITICAL, CRITICAL, CRITICAL)
	upQuery := dbc.NewSelect().Model((*db.StatusHistory)(nil)).ColumnExpr("count(id)").
		Where("team = ? and service = ? and put_flag_status = ? and check_status = ? and get_flag_status in (?, ?)",
			team, service, OK, OK, OK, NOT_CHECKED)
	if err := dbc.NewSelect().ColumnExpr("(?)", totQuery).ColumnExpr("(?)", upQuery).Scan(ctx, &totSla, &upSla); err != nil {
		log.Errorf("Error fetching sla status: %v", err)
		return 0.0, 0, 0, err
	}
	if totSla == 0 {
		return 1.0, 0, 0, nil
	}
	return float64(upSla) / float64(totSla), totSla, upSla, nil
}

type teamMapping struct {
	ID    int
	IP    string
	NetIP net.IP
}

func sortedTeamMappings() []teamMapping {
	teams := gs.Teams()
	mappings := make([]teamMapping, 0, len(teams))
	for _, team := range teams {
		mappings = append(mappings, teamMapping{
			ID:    team.ID,
			IP:    team.IP,
			NetIP: net.ParseIP(team.IP),
		})
	}
	sort.Slice(mappings, func(i, j int) bool {
		return bytes.Compare(mappings[i].NetIP, mappings[j].NetIP) < 0
	})
	return mappings
}

// runServiceRound submits every checker job of one (team, service) pair and
// writes the resulting status row once the round is over.
func runServiceRound(tm teamMapping, service string, currentRound uint, roundDeadline time.Time, wg *sync.WaitGroup) {
	defer wg.Done()

	settings := gs.Settings()
	ctx := context.Background()

	validFlags := make([]db.Flag, 0)
	if err := conn.NewSelect().Model(&validFlags).
		Where("team = ? and service = ? and ? - round < ?", tm.IP, service, currentRound, settings.FlagExpireTicks).
		Scan(ctx); err != nil {
		log.Errorf("Error fetching valid flags: %v", err)
		return
	}

	newFlag := genCheckFlag(tm.IP, service, currentRound)

	statusData := db.StatusHistory{
		Team:    tm.IP,
		Service: service,
		Round:   currentRound,
		// Defaults for a GET_FLAG that may never run (first rounds).
		GetFlagStatus:  NOT_CHECKED,
		GetFlagMessage: "There was no flag to check",
		GetFlagAt:      time.Now(),
	}

	// Spread the checks over the round, leaving room for the checker timeout.
	checkerTimeout := gs.CheckerTimeout()
	window := time.Until(roundDeadline) - checkerTimeout - 5*time.Second
	if window < 0 {
		window = 0
	}

	type pending struct {
		action string
		ch     chan JobResult
	}
	waiting := make([]pending, 0, len(validFlags)+2)

	submit := func(action string, flag string) {
		job := &Job{
			Round:     currentRound,
			TeamID:    tm.ID,
			TeamIP:    tm.IP,
			Service:   service,
			Action:    action,
			Flag:      flag,
			Timeout:   int64(checkerTimeout / time.Second),
			NotBefore: time.Now().Add(randomOffset(window)),
			Deadline:  roundDeadline,
		}
		waiting = append(waiting, pending{action: action, ch: dispatcher.Submit(job)})
	}

	submit(PUT_FLAG, newFlag)
	submit(CHECK_SLA, "")
	for _, flag := range validFlags {
		submit(GET_FLAG, flag.ID)
	}

	var lock sync.Mutex
	var jobsWg sync.WaitGroup
	jobsWg.Add(len(waiting))
	for _, p := range waiting {
		go func(p pending) {
			defer jobsWg.Done()
			var res JobResult
			select {
			case res = <-p.ch:
			case <-time.After(time.Until(roundDeadline) + 10*time.Second):
				res = JobResult{Status: KILLED, Message: "Checker never reported back"}
			}

			lock.Lock()
			defer lock.Unlock()
			switch p.action {
			case PUT_FLAG:
				statusData.PutFlagStatus = res.Status
				statusData.PutFlagMessage = res.Message
				statusData.PutFlagAt = time.Now()
				if res.Status != OK {
					// The flag never made it into the service: forget about it.
					if _, err := conn.NewDelete().Model(&db.Flag{}).Where("id = ?", newFlag).Exec(ctx); err != nil {
						log.Criticalf("Error deleting flag of %v on %v: %v", tm.IP, service, err)
					}
				}
			case GET_FLAG:
				// Overwrite the "nothing to check" default, then keep the
				// first failure.
				if statusData.GetFlagStatus == NOT_CHECKED || statusData.GetFlagStatus == OK {
					statusData.GetFlagStatus = res.Status
					statusData.GetFlagMessage = res.Message
					statusData.GetFlagAt = time.Now()
				}
			case CHECK_SLA:
				statusData.CheckStatus = res.Status
				statusData.CheckMessage = res.Message
				statusData.CheckdAt = time.Now()
			}
		}(p)
	}

	jobsWg.Wait()
	waitForRound(currentRound) // only publish the status when the round is over

	err := conn.RunInTx(ctx, nil, func(ctx context.Context, tx bun.Tx) error {
		if _, err := tx.NewInsert().Model(&statusData).Exec(ctx); err != nil {
			log.Criticalf("Error inserting sla status %v on %v: %v", tm.IP, service, err)
			return err
		}
		var err error
		if statusData.Sla, statusData.SlaTotTimes, statusData.SlaUpTimes, err = calcSLA(tx, ctx, tm.IP, service); err != nil {
			return err
		}
		if err := tx.NewSelect().ColumnExpr("score, offense, defense").Model((*db.ServiceScore)(nil)).
			Where("team = ? and service = ?", tm.IP, service).
			Scan(ctx, &statusData.Score, &statusData.OffensePoints, &statusData.DefensePoints); err != nil {
			log.Criticalf("Error fetching score %v on %v: %v", tm.IP, service, err)
			return err
		}
		if err := tx.NewSelect().Model((*db.FlagSubmission)(nil)).ColumnExpr("count(*)").
			Join("JOIN flags flag ON flag.id = submit.flag_id").
			Where("submit.team = ? and flag.service = ?", tm.IP, service).
			Scan(ctx, &statusData.StolenFlags); err != nil && err != sql.ErrNoRows {
			log.Errorf("Error fetching stolen flags: %v", err)
			return err
		}
		if err := tx.NewSelect().Model((*db.FlagSubmission)(nil)).ColumnExpr("count(*)").
			Join("JOIN flags flag ON flag.id = submit.flag_id").
			Where("flag.team = ? and flag.service = ?", tm.IP, service).
			Scan(ctx, &statusData.LostFlags); err != nil && err != sql.ErrNoRows {
			log.Errorf("Error fetching lost flags: %v", err)
			return err
		}
		if _, err := tx.NewUpdate().Model(&statusData).
			Where("team = ? and service = ? and round = ?", tm.IP, service, currentRound).
			Exec(ctx); err != nil {
			log.Criticalf("Error updating sla status %v on %v: %v", tm.IP, service, err)
			return err
		}
		return nil
	})
	if err != nil {
		log.Criticalf("Error storing status %v on %v: %v", tm.IP, service, err)
	}
}

func checkerRoutine() {
	var currentRound uint = 0

	if gs.GameEnded() {
		log.Infof("Game ended")
		if err := CtfRouteLock(); err != nil {
			log.Errorf("Error locking routes: %v", err)
		}
		return
	}

	wasRunning := false
	isInGrace := false

	if time.Now().After(gs.StartTime()) {
		log.Infof("Game already started!")
		if err := CtfRouteUnlock(); err != nil {
			log.Errorf("Error unlocking routes: %v", err)
		}
		wasRunning = true
		currentRound = uint(time.Since(gs.StartTime()) / gs.RoundLen())
	} else if time.Now().After(gs.StartTime().Add(-gs.GraceDuration())) {
		log.Infof("Game in grace period!")
		if err := CtfRouteLock(); err != nil {
			log.Errorf("Error locking routes: %v", err)
		}
		isInGrace = true
	}

	if currentRound > 0 {
		lastRoundExposed := db.GetExposedRound()
		// Data after the last exposed round is probably half written.
		if _, err := conn.NewDelete().Model((*db.Flag)(nil)).Where("round > ?", lastRoundExposed).Exec(context.Background()); err != nil {
			log.Criticalf("Error deleting flags for round %v: %v", currentRound, err)
		}
		if _, err := conn.NewDelete().Model((*db.StatusHistory)(nil)).Where("round > ?", lastRoundExposed).Exec(context.Background()); err != nil {
			log.Criticalf("Error deleting status for round %v: %v", currentRound, err)
		}
		currentRound++
		waitForRound(currentRound)
		if !wasRunning {
			if err := CtfRouteUnlock(); err != nil {
				log.Errorf("Error unlocking routes: %v", err)
			}
		}
	} else {
		if !isInGrace {
			waitForGraceTime()
			if err := CtfRouteLock(); err != nil {
				log.Errorf("Error locking routes: %v", err)
			}
		}
		waitForRound(0)
		if err := CtfRouteUnlock(); err != nil {
			log.Errorf("Error unlocking routes: %v", err)
		}
	}

	log.Infof("Starting checker loop with round %v", currentRound)

	for {
		waitWhilePaused()

		if gs.GameEnded() {
			log.Infof("Game ended")
			if err := CtfRouteLock(); err != nil {
				log.Errorf("Error locking routes: %v", err)
			}
			break
		}

		applyScheduledFreeze(currentRound)

		roundDeadline := calcRoundStartTime(currentRound + 1)
		teams := sortedTeamMappings()
		services := gs.CheckedServices()

		if len(teams) == 0 || len(services) == 0 {
			log.Warningf("Nothing to check on round %v (%d teams, %d services)", currentRound, len(teams), len(services))
		}

		log.Infof("Round %v: dispatching %d checks over %d workers (%d slots)",
			currentRound, len(teams)*len(services), len(registry.List()), registry.Capacity())

		var wg sync.WaitGroup
		wg.Add(len(teams) * len(services))
		for _, tm := range teams {
			for _, service := range services {
				go runServiceRound(tm, service, currentRound, roundDeadline, &wg)
			}
		}

		wg.Wait()
		waitForRound(currentRound + 1)
		currentRound++
		db.SetExposedRound(int64(currentRound - 1))
		pruneJobs(currentRound, 5)

		invalidateAllCaches()
	}
}

// applyScheduledFreeze flips the scoreboard into frozen mode when the planned
// freeze time is reached.
func applyScheduledFreeze(currentRound uint) {
	settings := gs.Settings()
	if settings.ScoreboardFrozen || settings.ScoreboardFreezeAt == nil {
		return
	}
	if time.Now().Before(*settings.ScoreboardFreezeAt) {
		return
	}
	freezeRound := int(currentRound) - 1
	if freezeRound < 0 {
		freezeRound = 0
	}
	gs.SetScoreboardFreeze(true, freezeRound)
	auditLog("system", "scoreboard.freeze", "", "scheduled freeze at round "+itoa(freezeRound))
	log.Warningf("Scoreboard frozen at round %v", freezeRound)
}

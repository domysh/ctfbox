package main

import (
	"context"
	"database/sql"
	"encoding/json"
	"fmt"
	"math"
	"net/http"
	"strings"
	"sync"
	"time"

	"game/db"
	"game/log"

	"github.com/gorilla/mux"
	"github.com/uptrace/bun"
)

type SubResp struct {
	Msg    string `json:"msg"`
	Flag   string `json:"flag"`
	Status string `json:"status"`
	// Reason is the machine readable version of Msg, for the admin panel.
	// Deliberately kept out of the players' API.
	Reason string `json:"-"`
}

// Reasons a submission ended the way it did.
const (
	reasonAccepted  = "accepted"
	reasonInvalid   = "invalid"
	reasonNop       = "nop"
	reasonBanned    = "banned"
	reasonOwn       = "own"
	reasonExpired   = "expired"
	reasonDuplicate = "duplicate"
	reasonError     = "error"
	reasonRateLimit = "rate-limited"
)

// One lock per team so that a team cannot race itself, plus a global lock
// around the score transaction.
var (
	lockMap            = make(map[string]*sync.Mutex)
	lockMappingMutex   sync.Mutex
	lastSubmissionTime = make(map[string]time.Time)
	submissionTimeLock sync.Mutex
	scoreMutex         sync.Mutex
)

var scale float64 = 15 * math.Sqrt(5.0)
var norm float64 = math.Log(math.Log(5.0)) / 12.0

func teamLock(team string) *sync.Mutex {
	lockMappingMutex.Lock()
	defer lockMappingMutex.Unlock()
	if lockMap[team] == nil {
		lockMap[team] = new(sync.Mutex)
	}
	return lockMap[team]
}

func elaborateFlag(team *TeamState, flag string, resp *SubResp, round uint, settings Settings, ev *db.SubmissionEvent) {
	var ctx context.Context = context.Background()
	info := new(db.Flag)
	err := conn.NewSelect().Model(info).Where("id = ?", strings.Trim(flag, " \n\t\r")).Scan(ctx)
	if err != nil {
		resp.Msg = fmt.Sprintf("[%s] Denied: invalid flag", flag)
		resp.Status = "DENIED"
		resp.Reason = reasonInvalid
		return
	}
	ev.Victim = info.Team
	ev.Service = info.Service
	if victim := gs.TeamByIP(info.Team); victim != nil {
		ev.VictimID = victim.ID
	}
	if team == nil {
		resp.Msg = fmt.Sprintf("[%s] Denied: invalid team", flag)
		resp.Status = "DENIED"
		resp.Reason = reasonInvalid
		return
	}
	victim := gs.TeamByIP(info.Team)
	if team.Nop || victim == nil || victim.Nop {
		resp.Msg = fmt.Sprintf("[%s] Denied: flag from nop team", flag)
		resp.Status = "DENIED"
		resp.Reason = reasonNop
		return
	}
	if victim.GameBanned {
		resp.Msg = fmt.Sprintf("[%s] Denied: flag from a banned team", flag)
		resp.Status = "DENIED"
		resp.Reason = reasonBanned
		return
	}
	if info.Team == team.IP {
		resp.Msg = fmt.Sprintf("[%s] Denied: flag is your own", flag)
		resp.Status = "DENIED"
		resp.Reason = reasonOwn
		return
	}
	if int64(round)-int64(info.Round) >= settings.FlagExpireTicks {
		resp.Msg = fmt.Sprintf("[%s] Denied: flag too old", flag)
		resp.Status = "DENIED"
		resp.Reason = reasonExpired
		return
	}
	flagSubmission := new(db.FlagSubmission)
	if err = conn.NewSelect().Model(flagSubmission).Where("team = ? and flag_id = ?", team.IP, info.ID).Scan(ctx); err != nil {
		if err != sql.ErrNoRows {
			log.Errorf("Error fetching flag submission: %v", err)
			resp.Msg = fmt.Sprintf("[%s] Error: notify the organizers and retry later", flag)
			resp.Status = "ERROR"
			resp.Reason = reasonError
			return
		}
	} else {
		resp.Msg = fmt.Sprintf("[%s] Denied: flag already submitted", flag)
		resp.Status = "DENIED"
		resp.Reason = reasonDuplicate
		return
	}

	// Score movements are computed in a transaction to keep the two service
	// scores consistent with the submission row.
	scoreMutex.Lock()
	var offensePoints float64
	err = conn.RunInTx(ctx, nil, func(ctx context.Context, tx bun.Tx) error {
		attackerScore := new(db.ServiceScore)
		victimScore := new(db.ServiceScore)
		if err := tx.NewSelect().Model(attackerScore).Where("team = ? and service = ?", team.IP, info.Service).Scan(ctx); err != nil {
			return err
		}
		if err := tx.NewSelect().Model(victimScore).Where("team = ? and service = ?", info.Team, info.Service).Scan(ctx); err != nil {
			return err
		}
		offensePoints = scale / (1 + math.Exp((math.Sqrt(attackerScore.Score)-math.Sqrt(victimScore.Score))*norm))
		defensePoints := min(victimScore.Score, offensePoints)

		if _, err := tx.NewInsert().Model(&db.FlagSubmission{
			FlagID:          info.ID,
			Team:            team.IP,
			Round:           round,
			OffensivePoints: offensePoints,
			DefensivePoints: defensePoints,
		}).Exec(ctx); err != nil {
			return err
		}
		if _, err := tx.NewUpdate().Model(attackerScore).WherePK().Set("score = score + ?", offensePoints).Set("offense = offense + ?", offensePoints).Exec(ctx); err != nil {
			return err
		}
		if _, err := tx.NewUpdate().Model(victimScore).WherePK().Set("score = score - ?", defensePoints).Set("defense = defense - ?", defensePoints).Exec(ctx); err != nil {
			return err
		}
		return nil
	})
	scoreMutex.Unlock()

	if err != nil {
		resp.Msg = fmt.Sprintf("[%s] Error: notify the organizers and retry later", flag)
		resp.Status = "ERROR"
		resp.Reason = reasonError
		log.Errorf("Error submitting flag: %v", err)
		return
	}

	resp.Status = "ACCEPTED"
	resp.Reason = reasonAccepted
	ev.Points = offensePoints
	resp.Msg = fmt.Sprintf("[%s] Accepted: %f flag points", flag, offensePoints)
	log.Debugf("Flag %s from %s: %.02f flag points", flag, team.Name, offensePoints)
}

func elaborateFlags(team *TeamState, submittedFlags []string, round uint, settings Settings) []SubResp {
	responses := make([]SubResp, 0, len(submittedFlags))
	for _, flag := range submittedFlags {
		resp := SubResp{
			Flag:   flag,
			Status: "RESUBMIT", // Default status
			Reason: reasonError,
			Msg:    fmt.Sprintf("[%s] Unexpected Error, retry to send later", flag),
		}
		ev := newSubmissionEvent(team, flag, round)
		elaborateFlag(team, flag, &resp, round, settings, ev)
		ev.Status = resp.Status
		ev.Reason = resp.Reason
		recordSubmission(ev)
		responses = append(responses, resp)
	}
	return responses
}

func submitFlags(w http.ResponseWriter, r *http.Request) {
	settings := gs.Settings()

	if gs.GameEnded() {
		w.WriteHeader(http.StatusServiceUnavailable)
		return
	}
	if settings.GamePaused {
		w.WriteHeader(http.StatusServiceUnavailable)
		return
	}

	teamToken := r.Header.Get("X-Team-Token")
	currentTick := db.GetExposedRound()
	if currentTick < 0 {
		w.WriteHeader(http.StatusServiceUnavailable)
		return
	}

	teamInfo := gs.TeamByToken(teamToken)
	if teamInfo == nil || teamInfo.Nop {
		w.WriteHeader(http.StatusUnauthorized)
		return
	}
	if teamInfo.GameBanned {
		w.WriteHeader(http.StatusForbidden)
		if err := json.NewEncoder(w).Encode([]SubResp{{
			Status: "DENIED",
			Msg:    "Your team is banned from flag submission: " + teamInfo.BanReason,
		}}); err != nil {
			log.Debugf("Error encoding ban response: %v", err)
		}
		return
	}

	lock := teamLock(teamInfo.IP)
	lock.Lock()
	defer lock.Unlock()

	if settings.SubmissionTimeout != nil {
		limit := time.Duration(*settings.SubmissionTimeout * float64(time.Second))
		submissionTimeLock.Lock()
		lastSubmitTime, ok := lastSubmissionTime[teamInfo.IP]
		if ok && time.Since(lastSubmitTime) < limit {
			submissionTimeLock.Unlock()
			log.Debugf("Submission limit reached for team %s", teamInfo.IP)
			ev := newSubmissionEvent(teamInfo, "", uint(currentTick))
			ev.Status = "DENIED"
			ev.Reason = reasonRateLimit
			recordSubmission(ev)
			w.WriteHeader(http.StatusTooManyRequests)
			return
		}
		lastSubmissionTime[teamInfo.IP] = time.Now()
		submissionTimeLock.Unlock()
	}

	var submittedFlags []string
	if err := json.NewDecoder(r.Body).Decode(&submittedFlags); err != nil {
		w.WriteHeader(http.StatusBadRequest)
		return
	}

	submittedFlags = submittedFlags[:min(len(submittedFlags), settings.MaxFlagsPerRequest)]
	responses := elaborateFlags(teamInfo, submittedFlags, uint(currentTick), settings)

	w.Header().Set("Content-Type", "application/json")
	if err := json.NewEncoder(w).Encode(responses); err != nil {
		w.WriteHeader(http.StatusInternalServerError)
	}
}

func serveSubmission() {
	router := mux.NewRouter()
	router.HandleFunc("/flags", submitFlags).Methods("PUT")

	log.Noticef("Starting flag submission server on :8080")

	srv := &http.Server{
		Handler:      compressMiddleware(router),
		Addr:         "0.0.0.0:8080",
		WriteTimeout: 30 * time.Second,
		ReadTimeout:  30 * time.Second,
	}

	log.Fatal(srv.ListenAndServe())
}

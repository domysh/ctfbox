package main

import (
	"context"
	"encoding/json"
	"net/http"
	"os"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
	"sync"
	"time"

	"game/db"
	"game/log"

	"github.com/gorilla/mux"
	"github.com/rs/cors"
	"github.com/uptrace/bun"
)

// apiCache keeps one rendered JSON response per round.
//
// The generation counter closes a race that is easy to miss: a request that
// started rendering before something changed would otherwise store its stale
// answer after the invalidation, and serve it for a whole round. It bites
// exactly on the things that change between rounds - the network state, the
// scoreboard freeze - which are the ones players notice immediately.
type apiCache struct {
	data        []byte
	lastUpdated time.Time
	round       int
	generation  uint64
	mutex       sync.RWMutex
}

// begin marks the start of a render; pass what it returns to update.
func (c *apiCache) begin() uint64 {
	c.mutex.RLock()
	defer c.mutex.RUnlock()
	return c.generation
}

var (
	scoreboardCache = &apiCache{}
	chartCache      = &apiCache{}
	statusCache     = &apiCache{}
	teamCaches      = make(map[string]*apiCache)
	teamCachesMutex sync.RWMutex
)

func invalidateAllCaches() {
	scoreboardCache.invalidate()
	chartCache.invalidate()
	statusCache.invalidate()

	teamCachesMutex.Lock()
	for _, cache := range teamCaches {
		cache.invalidate()
	}
	teamCachesMutex.Unlock()
	invalidateFlagIDsCache()
	log.Debugf("All API caches invalidated")
}

func (c *apiCache) invalidate() {
	c.mutex.Lock()
	c.generation++
	c.round = -1
	c.data = nil
	c.mutex.Unlock()
}

func (c *apiCache) isValid(currentRound int) bool {
	c.mutex.RLock()
	defer c.mutex.RUnlock()
	return c.round == currentRound && c.data != nil && time.Since(c.lastUpdated) < 60*time.Second
}

func (c *apiCache) update(data []byte, round int, generation uint64) {
	c.mutex.Lock()
	defer c.mutex.Unlock()
	if c.generation != generation {
		return // something changed while we were rendering: do not cache this
	}
	c.data = data
	c.round = round
	c.lastUpdated = time.Now()
}

func (c *apiCache) serve(w http.ResponseWriter) {
	c.mutex.RLock()
	defer c.mutex.RUnlock()
	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("X-Cache", "HIT")
	w.Write(c.data)
}

type ServiceRoundStatus struct {
	Service             string  `json:"service"`
	StolenFlags         uint    `json:"stolen_flags"`
	DiffStolenFlags     int     `json:"diff_stolen_flags"`
	LostFlags           uint    `json:"lost_flags"`
	DiffLostFlags       int     `json:"diff_lost_flags"`
	OffensivePoints     float64 `json:"offensive_points"`
	DiffOffensivePoints float64 `json:"diff_offensive_points"`
	DefensivePoints     float64 `json:"defensive_points"`
	DiffDefensivePoints float64 `json:"diff_defensive_points"`
	Sla                 float64 `json:"sla"`
	DiffSla             float64 `json:"diff_sla"`
	Score               float64 `json:"score"`
	DiffScore           float64 `json:"diff_score"`
	TicksUp             uint    `json:"ticks_up"`
	TicksDown           uint    `json:"ticks_down"`
	PutFlag             int     `json:"put_flag"`
	PutFlagMsg          string  `json:"put_flag_msg"`
	GetFlag             int     `json:"get_flag"`
	GetFlagMsg          string  `json:"get_flag_msg"`
	SlaCheck            int     `json:"sla_check"`
	SlaCheckMsg         string  `json:"sla_check_msg"`
	FinalScore          float64 `json:"final_score"`
	DiffFinalScore      float64 `json:"diff_final_score"`
}

type TeamRoundStatus struct {
	Team     string               `json:"team"`
	Score    float64              `json:"score"`
	Services []ServiceRoundStatus `json:"services"`
}

type TeamRoundStatusShort struct {
	Team  string  `json:"team"`
	Score float64 `json:"score"`
}

type ChartAPIResponse struct {
	Round  uint                   `json:"round"`
	Scores []TeamRoundStatusShort `json:"scores"`
}

type ScoreboardAPIResponse struct {
	Round       uint              `json:"round"`
	Frozen      bool              `json:"frozen"`
	FreezeRound int               `json:"freeze_round"`
	Scores      []TeamRoundStatus `json:"scores"`
}

type TeamAPIResponse struct {
	Round uint            `json:"round"`
	Score TeamRoundStatus `json:"score"`
}

// scoreRound decides which round's numbers must be published: while the
// scoreboard is frozen the ranking sticks to the freeze round, while SLA and
// service status keep coming from the live round.
func scoreRound(currentRound int) (round int, frozen bool) {
	settings := gs.Settings()
	if settings.ScoreboardFrozen && settings.ScoreboardFreezeRd >= 0 && settings.ScoreboardFreezeRd < currentRound {
		return settings.ScoreboardFreezeRd, true
	}
	return currentRound, settings.ScoreboardFrozen
}

// roundIndex holds every status row of one round, grouped by team and service.
type roundIndex map[string]map[string]*db.StatusHistory

func (r roundIndex) get(team string) map[string]*db.StatusHistory {
	if r == nil {
		return nil
	}
	return r[team]
}

// fetchRounds loads a handful of rounds in a single query. Querying one round
// per team turns into hundreds of round trips on a real competition.
func fetchRounds(ctx context.Context, rounds []int) (map[int]roundIndex, error) {
	wanted := make([]int, 0, len(rounds))
	seen := make(map[int]bool, len(rounds))
	for _, round := range rounds {
		if round < 0 || seen[round] {
			continue
		}
		seen[round] = true
		wanted = append(wanted, round)
	}
	result := make(map[int]roundIndex, len(wanted))
	if len(wanted) == 0 {
		return result, nil
	}

	rows := make([]db.StatusHistory, 0)
	if err := conn.NewSelect().Model(&rows).Where("round IN (?)", bun.In(wanted)).Scan(ctx); err != nil {
		return nil, err
	}
	for i := range rows {
		row := &rows[i]
		round := int(row.Round)
		if result[round] == nil {
			result[round] = make(roundIndex)
		}
		if result[round][row.Team] == nil {
			result[round][row.Team] = make(map[string]*db.StatusHistory)
		}
		result[round][row.Team][row.Service] = row
	}
	return result, nil
}

// fetchTeamHistory loads the whole history of one team in a single query.
func fetchTeamHistory(ctx context.Context, team string, upToRound int) (map[int]map[string]*db.StatusHistory, error) {
	rows := make([]db.StatusHistory, 0)
	if err := conn.NewSelect().Model(&rows).
		Where("team = ? and round <= ?", team, upToRound).
		Order("round ASC").Scan(ctx); err != nil {
		return nil, err
	}
	history := make(map[int]map[string]*db.StatusHistory)
	for i := range rows {
		row := &rows[i]
		round := int(row.Round)
		if history[round] == nil {
			history[round] = make(map[string]*db.StatusHistory)
		}
		history[round][row.Service] = row
	}
	return history, nil
}

// makeServiceStatus merges the live status (SLA, up/down) with the score row
// (which is a past round while the scoreboard is frozen).
func makeServiceStatus(live, livePrev, score, scorePrev *db.StatusHistory, weight float64) ServiceRoundStatus {
	out := ServiceRoundStatus{Service: live.Service}

	// Live half: what the players are still allowed to see while frozen.
	out.Sla = live.Sla
	out.TicksUp = live.SlaUpTimes
	out.TicksDown = live.SlaTotTimes - live.SlaUpTimes
	out.PutFlag = live.PutFlagStatus
	out.PutFlagMsg = live.PutFlagMessage
	out.GetFlag = live.GetFlagStatus
	out.GetFlagMsg = live.GetFlagMessage
	out.SlaCheck = live.CheckStatus
	out.SlaCheckMsg = live.CheckMessage
	if livePrev != nil {
		out.DiffSla = live.Sla - livePrev.Sla
	}

	// Frozen half: everything that would reveal the ranking.
	out.StolenFlags = score.StolenFlags
	out.LostFlags = score.LostFlags
	out.OffensivePoints = score.OffensePoints
	out.DefensivePoints = score.DefensePoints
	out.Score = score.Score
	out.FinalScore = score.Score * score.Sla * weight
	if scorePrev != nil {
		out.DiffStolenFlags = int(score.StolenFlags) - int(scorePrev.StolenFlags)
		out.DiffLostFlags = int(score.LostFlags) - int(scorePrev.LostFlags)
		out.DiffOffensivePoints = score.OffensePoints - scorePrev.OffensePoints
		out.DiffDefensivePoints = score.DefensePoints - scorePrev.DefensePoints
		out.DiffScore = score.Score - scorePrev.Score
		out.DiffFinalScore = out.FinalScore - (scorePrev.Score * scorePrev.Sla * weight)
	}
	return out
}

// buildTeamRound assembles one scoreboard row out of already loaded rounds.
//
// `live` carries the SLA and the service status, `score` carries everything
// that would reveal the ranking: while the scoreboard is frozen those two come
// from different rounds, which is the whole point of the freeze.
func buildTeamRound(
	team string,
	live map[string]*db.StatusHistory,
	livePrev map[string]*db.StatusHistory,
	score map[string]*db.StatusHistory,
	scorePrev map[string]*db.StatusHistory,
) TeamRoundStatus {
	result := TeamRoundStatus{Team: team, Services: make([]ServiceRoundStatus, 0, len(live))}

	names := make([]string, 0, len(live))
	for name := range live {
		names = append(names, name)
	}
	sort.Strings(names)

	total := 0.0
	for _, name := range names {
		liveRow := live[name]
		scoreRow := score[name]
		if scoreRow == nil {
			// The service did not exist yet at the freeze round.
			scoreRow = liveRow
		}
		entry := makeServiceStatus(liveRow, livePrev[name], scoreRow, scorePrev[name], gs.ServiceWeight(name))
		result.Services = append(result.Services, entry)
		total += entry.FinalScore
	}
	result.Score = total
	return result
}

func handleScoreboard(w http.ResponseWriter, r *http.Request) {
	round := db.GetExposedRound()

	if round < 0 {
		writeJSON(w, ScoreboardAPIResponse{Round: 0, Scores: make([]TeamRoundStatus, 0)})
		return
	}
	generation := scoreboardCache.begin()
	if scoreboardCache.isValid(round) {
		scoreboardCache.serve(w)
		return
	}

	frozenRound, frozen := scoreRound(round)
	teams := gs.Teams()

	rounds, err := fetchRounds(r.Context(), []int{round, round - 1, frozenRound, frozenRound - 1})
	if err != nil {
		log.Errorf("Error fetching scoreboard rounds: %v", err)
		http.Error(w, "Internal server error", http.StatusInternalServerError)
		return
	}

	response := ScoreboardAPIResponse{
		Round:       uint(round),
		Frozen:      frozen,
		FreezeRound: frozenRound,
		Scores:      make([]TeamRoundStatus, 0, len(teams)),
	}
	for _, team := range teams {
		response.Scores = append(response.Scores, buildTeamRound(
			team.IP,
			rounds[round].get(team.IP),
			rounds[round-1].get(team.IP),
			rounds[frozenRound].get(team.IP),
			rounds[frozenRound-1].get(team.IP),
		))
	}

	jsonData, err := json.Marshal(response)
	if err != nil {
		log.Errorf("Error encoding response: %v", err)
		http.Error(w, "Internal server error", http.StatusInternalServerError)
		return
	}
	scoreboardCache.update(jsonData, round, generation)

	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("X-Cache", "MISS")
	w.Write(jsonData)
}

func handleChart(w http.ResponseWriter, r *http.Request) {
	round := db.GetExposedRound()
	if round < 0 {
		writeJSON(w, []ChartAPIResponse{})
		return
	}
	generation := chartCache.begin()
	if chartCache.isValid(round) {
		chartCache.serve(w)
		return
	}
	if len(gs.Teams()) == 0 {
		writeJSON(w, []ChartAPIResponse{})
		return
	}

	// While frozen the chart stops at the freeze round, otherwise the ranking
	// would leak through the curves.
	lastRound, _ := scoreRound(round)

	weights := make(map[string]float64)
	for _, svc := range gs.Services() {
		weight := svc.Weight
		if weight <= 0 {
			weight = 1
		}
		weights[svc.Name] = weight
	}

	rows := make([]db.StatusHistory, 0)
	if err := conn.NewSelect().Model(&rows).
		Column("round", "team", "service", "score", "sla").
		Where("round <= ?", lastRound).
		Order("round ASC").Scan(r.Context()); err != nil {
		log.Errorf("Error fetching chart data: %v", err)
		http.Error(w, "Internal server error", http.StatusInternalServerError)
		return
	}

	totals := make([]map[string]float64, lastRound+1)
	order := make([][]string, lastRound+1)
	for i := range totals {
		totals[i] = make(map[string]float64)
	}
	for i := range rows {
		row := &rows[i]
		index := int(row.Round)
		if index < 0 || index > lastRound {
			continue
		}
		weight, ok := weights[row.Service]
		if !ok {
			weight = 1
		}
		if _, seen := totals[index][row.Team]; !seen {
			order[index] = append(order[index], row.Team)
		}
		totals[index][row.Team] += row.Score * row.Sla * weight
	}

	response := make([]ChartAPIResponse, 0, lastRound+1)
	for i := 0; i <= lastRound; i++ {
		scores := make([]TeamRoundStatusShort, 0, len(order[i]))
		for _, team := range order[i] {
			scores = append(scores, TeamRoundStatusShort{Team: team, Score: totals[i][team]})
		}
		response = append(response, ChartAPIResponse{Round: uint(i), Scores: scores})
	}

	jsonData, err := json.Marshal(response)
	if err != nil {
		log.Errorf("Error encoding response: %v", err)
		http.Error(w, "Internal server error", http.StatusInternalServerError)
		return
	}
	chartCache.update(jsonData, round, generation)

	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("X-Cache", "MISS")
	w.Write(jsonData)
}

func handleTeam(w http.ResponseWriter, r *http.Request) {
	teamId, err := strconv.Atoi(mux.Vars(r)["team_id"])
	if err != nil {
		http.Error(w, "Invalid team ID", http.StatusBadRequest)
		return
	}
	teamInfo := gs.TeamByID(teamId)
	if teamInfo == nil {
		http.Error(w, "Invalid team ID", http.StatusBadRequest)
		return
	}
	round := db.GetExposedRound()
	if round < 0 {
		writeJSON(w, []TeamAPIResponse{})
		return
	}

	teamCacheKey := strconv.Itoa(teamId)
	teamCachesMutex.Lock()
	cache, exists := teamCaches[teamCacheKey]
	if !exists {
		cache = &apiCache{}
		teamCaches[teamCacheKey] = cache
	}
	teamCachesMutex.Unlock()

	generation := cache.begin()
	if cache.isValid(round) {
		cache.serve(w)
		return
	}

	frozenRound, _ := scoreRound(round)
	history, err := fetchTeamHistory(r.Context(), teamInfo.IP, round)
	if err != nil {
		log.Errorf("Error fetching scores for team %s: %v", teamInfo.IP, err)
		http.Error(w, "Internal server error", http.StatusInternalServerError)
		return
	}

	response := make([]TeamAPIResponse, 0, round+1)
	for i := 0; i <= round; i++ {
		scoreAt := i
		if i > frozenRound {
			scoreAt = frozenRound
		}
		response = append(response, TeamAPIResponse{
			Round: uint(i),
			Score: buildTeamRound(
				teamInfo.IP,
				history[i],
				history[i-1],
				history[scoreAt],
				history[scoreAt-1],
			),
		})
	}

	jsonData, err := json.Marshal(response)
	if err != nil {
		log.Errorf("Error encoding response: %v", err)
		http.Error(w, "Internal server error", http.StatusInternalServerError)
		return
	}
	cache.update(jsonData, round, generation)

	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("X-Cache", "MISS")
	w.Write(jsonData)
}

type TeamStatus struct {
	Id        int    `json:"id"`
	Name      string `json:"name"`
	ShortName string `json:"shortname"`
	Host      string `json:"host"`
	Image     string `json:"image"`
	Nop       bool   `json:"nop"`
	Banned    bool   `json:"banned"`
}

type ServiceStatus struct {
	Name    string  `json:"name"`
	Enabled bool    `json:"enabled"`
	Weight  float64 `json:"weight"`
}

type StatusAPIResponse struct {
	Teams               []TeamStatus    `json:"teams"`
	Services            []ServiceStatus `json:"services"`
	StartTime           string          `json:"start"`
	StartGraceTime      string          `json:"start_grace"`
	EndTime             *string         `json:"end"`
	RoundLen            uint            `json:"roundTime"`
	FlagExpireTicks     uint            `json:"flag_expire_ticks"`
	SubmitterFlagsLimit uint            `json:"submitter_flags_limit"`
	SubmitterRateLimit  *float64        `json:"submitter_rate_limit"`
	CurrentRound        int             `json:"current_round"`
	FlagRegex           string          `json:"flag_regex"`
	InitServicePoints   float64         `json:"init_service_points"`
	ScoreboardFrozen    bool            `json:"scoreboard_frozen"`
	ScoreboardFreezeAt  *string         `json:"scoreboard_freeze_time"`
	FreezeRound         int             `json:"freeze_round"`
	GamePaused          bool            `json:"game_paused"`
	NetworkState        string          `json:"network_state"`
}

func handleStatus(w http.ResponseWriter, r *http.Request) {
	round := db.GetExposedRound()

	generation := statusCache.begin()
	if statusCache.isValid(round) {
		statusCache.serve(w)
		return
	}

	settings := gs.Settings()
	teams := make([]TeamStatus, 0)
	for _, team := range gs.Teams() {
		teams = append(teams, TeamStatus{
			Id:        team.ID,
			Name:      team.Name,
			Host:      team.IP,
			ShortName: strings.ToLower(strings.ReplaceAll(team.Name, " ", "_")),
			Image:     team.Image,
			Nop:       team.Nop,
			Banned:    team.GameBanned || team.NetworkBanned,
		})
	}
	services := make([]ServiceStatus, 0)
	for _, svc := range gs.Services() {
		services = append(services, ServiceStatus{Name: svc.Name, Enabled: svc.Enabled, Weight: svc.Weight})
	}

	var endTime *string
	if settings.EndTime != nil {
		formatted := settings.EndTime.Format(time.RFC3339)
		endTime = &formatted
	}
	var freezeAt *string
	if settings.ScoreboardFreezeAt != nil {
		formatted := settings.ScoreboardFreezeAt.Format(time.RFC3339)
		freezeAt = &formatted
	}

	response := StatusAPIResponse{
		Teams:               teams,
		Services:            services,
		StartTime:           gs.StartTime().Format(time.RFC3339),
		StartGraceTime:      gs.StartTime().Add(-gs.GraceDuration()).Format(time.RFC3339),
		EndTime:             endTime,
		RoundLen:            uint(gs.RoundLen() / time.Second),
		FlagExpireTicks:     uint(settings.FlagExpireTicks),
		SubmitterFlagsLimit: uint(settings.MaxFlagsPerRequest),
		SubmitterRateLimit:  settings.SubmissionTimeout,
		CurrentRound:        round,
		FlagRegex:           settings.FlagRegex,
		InitServicePoints:   settings.InitialServiceScore,
		ScoreboardFrozen:    settings.ScoreboardFrozen,
		ScoreboardFreezeAt:  freezeAt,
		FreezeRound:         settings.ScoreboardFreezeRd,
		GamePaused:          settings.GamePaused,
		NetworkState:        gs.NetworkState(),
	}

	jsonData, err := json.Marshal(response)
	if err != nil {
		log.Errorf("Error encoding response: %v", err)
		http.Error(w, "Internal server error", http.StatusInternalServerError)
		return
	}
	statusCache.update(jsonData, round, generation)

	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("X-Cache", "MISS")
	w.Write(jsonData)
}

// handleAnnouncements exposes the organizers' broadcast messages to everybody.
func handleAnnouncements(w http.ResponseWriter, r *http.Request) {
	rows := make([]db.Announcement, 0)
	if err := conn.NewSelect().Model(&rows).Where("visible = TRUE").Order("at DESC").Limit(50).Scan(r.Context()); err != nil {
		log.Errorf("Error fetching announcements: %v", err)
		http.Error(w, "Internal server error", http.StatusInternalServerError)
		return
	}
	writeJSON(w, rows)
}

type spaHandler struct {
	staticPath string
	indexPath  string
}

func (h spaHandler) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	// Join internally calls path.Clean to prevent directory traversal
	path := filepath.Join(h.staticPath, r.URL.Path)

	fi, err := os.Stat(path)
	if os.IsNotExist(err) || (fi != nil && fi.IsDir()) {
		http.ServeFile(w, r, filepath.Join(h.staticPath, h.indexPath))
		return
	}
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}
	http.FileServer(http.Dir(h.staticPath)).ServeHTTP(w, r)
}

func serveScoreboard() {
	router := mux.NewRouter()

	router.HandleFunc("/api/scoreboard", handleScoreboard).Methods("GET")
	router.HandleFunc("/api/chart", handleChart).Methods("GET")
	router.HandleFunc("/api/team/{team_id}", handleTeam).Methods("GET")
	router.HandleFunc("/api/status", handleStatus).Methods("GET")
	router.HandleFunc("/api/announcements", handleAnnouncements).Methods("GET")

	registerAdminRoutes(router)

	log.Noticef("Starting scoreboard server on :80")
	spa := spaHandler{staticPath: "frontend", indexPath: "index.html"}
	router.PathPrefix("/").Handler(spa)

	var finalHandler http.Handler = router

	if conf.Debug {
		corsPolicy := cors.New(cors.Options{
			AllowedOrigins:   []string{"*"},
			AllowCredentials: true,
			AllowedHeaders:   []string{"*"},
			AllowedMethods:   []string{"GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"},
		})
		finalHandler = corsPolicy.Handler(router)
	}

	finalHandler = compressMiddleware(finalHandler)

	srv := &http.Server{
		Handler:      finalHandler,
		Addr:         "0.0.0.0:80",
		WriteTimeout: 60 * time.Second,
		ReadTimeout:  30 * time.Second,
	}

	log.Fatal(srv.ListenAndServe())
}

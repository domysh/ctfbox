package main

import (
	"context"
	"database/sql"
	"os"
	"sort"
	"strconv"
	"strings"
	"sync"
	"time"

	"game/db"
	"game/log"
)

// Settings holds every knob the organizers can turn while the game runs.
type Settings struct {
	TickTime            int64    `json:"tick_time"`
	FlagExpireTicks     int64    `json:"flag_expire_ticks"`
	InitialServiceScore float64  `json:"initial_service_score"`
	MaxFlagsPerRequest  int      `json:"max_flags_per_request"`
	SubmissionTimeout   *float64 `json:"submission_timeout"`
	GraceTime           int64    `json:"grace_time"`
	CheckerTimeout      int64    `json:"checker_timeout"`
	FlagRegex           string   `json:"flag_regex"`

	StartTime *time.Time `json:"start_time"`
	EndTime   *time.Time `json:"end_time"`

	// Scoreboard freeze: when active the ranking is served as it was at
	// FreezeRound while SLA and service status keep updating live.
	ScoreboardFreezeAt *time.Time `json:"scoreboard_freeze_time"`
	ScoreboardFrozen   bool       `json:"scoreboard_frozen"`
	ScoreboardFreezeRd int        `json:"scoreboard_freeze_round"`

	// GamePaused stops the checker loop without stopping the server.
	GamePaused bool `json:"game_paused"`
}

// TeamState is the runtime view of a team.
type TeamState struct {
	ID            int    `json:"id"`
	Name          string `json:"name"`
	Token         string `json:"-"`
	Image         string `json:"image"`
	Nop           bool   `json:"nop"`
	GameBanned    bool   `json:"game_banned"`
	NetworkBanned bool   `json:"network_banned"`
	BanReason     string `json:"ban_reason"`
	Node          string `json:"node"`
	IP            string `json:"ip"`
}

// ServiceState is the runtime view of a service.
type ServiceState struct {
	Name        string  `json:"name"`
	Enabled     bool    `json:"enabled"`
	Weight      float64 `json:"weight"`
	Description string  `json:"description"`
	Present     bool    `json:"present"`
}

type GameState struct {
	mu       sync.RWMutex
	settings Settings
	teams    []TeamState
	services []ServiceState
	// networkState mirrors the last command sent to the router.
	networkState string
	// suspendedProfiles are the VPN profiles the organizers cut off, by
	// address. Persisted for the same reason the network state is: a router
	// comes back with every peer from its wg0.conf and has to be told again.
	suspendedProfiles map[string]bool
}

var gs = &GameState{networkState: "unknown", suspendedProfiles: map[string]bool{}}

const (
	setTickTime         = "tick_time"
	setFlagExpireTicks  = "flag_expire_ticks"
	setInitialScore     = "initial_service_score"
	setMaxFlags         = "max_flags_per_request"
	setSubmissionTmo    = "submission_timeout"
	setGraceTime        = "grace_time"
	setCheckerTimeout   = "checker_timeout"
	setEndTime          = "end_time"
	setFreezeAt         = "scoreboard_freeze_time"
	setFrozen           = "scoreboard_frozen"
	setFreezeRound      = "scoreboard_freeze_round"
	setGamePaused       = "game_paused"
	setNetworkStateKey  = "network_state"
	setSuspendedVPNKey  = "vpn_suspended"
	setSettingsSeeded   = "settings_seeded"
	settingsSeededValue = "1"
)

func readSetting(key string) *string {
	conn := db.ConnectDB()
	row := new(db.Setting)
	if err := conn.NewSelect().Model(row).Where("key = ?", key).Scan(context.Background()); err != nil {
		if err == sql.ErrNoRows {
			return nil
		}
		log.Criticalf("Error reading setting %v: %v", key, err)
		return nil
	}
	return &row.Value
}

func writeSetting(key string, value string) {
	conn := db.ConnectDB()
	if _, err := conn.NewInsert().Model(&db.Setting{Key: key, Value: value, UpdatedAt: time.Now()}).
		On("CONFLICT (key) DO UPDATE").
		Set("value = EXCLUDED.value, updated_at = EXCLUDED.updated_at").
		Exec(context.Background()); err != nil {
		log.Criticalf("Error writing setting %v: %v", key, err)
	}
}

func settingInt(key string, fallback int64) int64 {
	raw := readSetting(key)
	if raw == nil {
		return fallback
	}
	parsed, err := strconv.ParseInt(*raw, 10, 64)
	if err != nil {
		return fallback
	}
	return parsed
}

func settingFloat(key string, fallback float64) float64 {
	raw := readSetting(key)
	if raw == nil {
		return fallback
	}
	parsed, err := strconv.ParseFloat(*raw, 64)
	if err != nil {
		return fallback
	}
	return parsed
}

func settingBool(key string, fallback bool) bool {
	raw := readSetting(key)
	if raw == nil {
		return fallback
	}
	return *raw == "1" || strings.EqualFold(*raw, "true")
}

func settingTime(key string, fallback *time.Time) *time.Time {
	raw := readSetting(key)
	if raw == nil {
		return fallback
	}
	if strings.TrimSpace(*raw) == "" {
		return nil
	}
	parsed, err := time.Parse(time.RFC3339, *raw)
	if err != nil {
		return fallback
	}
	return &parsed
}

func boolToSetting(v bool) string {
	if v {
		return "1"
	}
	return "0"
}

func timeToSetting(t *time.Time) string {
	if t == nil {
		return ""
	}
	return t.Format(time.RFC3339)
}

// ----------------------------------------------------------------------------
// bootstrap
// ----------------------------------------------------------------------------

// InitState seeds the database from config.json the first time and then loads
// the authoritative runtime state back from it.
func InitState(c *Config) {
	seeded := readSetting(setSettingsSeeded) != nil

	if !seeded {
		endTime, err := parseTimePtr(c.EndTime)
		if err != nil {
			log.Panicf("Error parsing end time: %v", err)
		}
		freezeAt, err := parseTimePtr(c.ScoreboardFreeze)
		if err != nil {
			log.Panicf("Error parsing scoreboard freeze time: %v", err)
		}
		grace := int64(0)
		if c.GraceTime != nil {
			grace = *c.GraceTime
		}
		checkerTimeout := c.CheckerTimeout
		if checkerTimeout <= 0 {
			checkerTimeout = 30
		}
		writeSetting(setTickTime, strconv.FormatInt(c.Round, 10))
		writeSetting(setFlagExpireTicks, strconv.FormatInt(c.FlagExpireTicks, 10))
		writeSetting(setInitialScore, strconv.FormatFloat(c.InitialServiceScore, 'f', -1, 64))
		writeSetting(setMaxFlags, strconv.Itoa(c.MaxFlagsPerRequest))
		if c.SubmitterTimeout != nil {
			writeSetting(setSubmissionTmo, strconv.FormatFloat(*c.SubmitterTimeout, 'f', -1, 64))
		} else {
			writeSetting(setSubmissionTmo, "")
		}
		writeSetting(setGraceTime, strconv.FormatInt(grace, 10))
		writeSetting(setCheckerTimeout, strconv.FormatInt(checkerTimeout, 10))
		writeSetting(setEndTime, timeToSetting(endTime))
		writeSetting(setFreezeAt, timeToSetting(freezeAt))
		writeSetting(setFrozen, "0")
		writeSetting(setFreezeRound, "-1")
		writeSetting(setGamePaused, "0")
		writeSetting(setSettingsSeeded, settingsSeededValue)
	}

	syncTeamsFromConfig(c)
	syncServicesFromDisk()
	ReloadState()
	ensureStartTime()
	initScoreboard()
}

// ensureStartTime resolves the game start once and stores it, so that a restart
// never shifts an already running competition.
func ensureStartTime() {
	if db.GetStartTime() == nil {
		if conf.StartTime != nil && strings.TrimSpace(*conf.StartTime) != "" {
			startTime, err := time.Parse(time.RFC3339, *conf.StartTime)
			if err != nil {
				log.Panicf("Error parsing start time: %v", err)
			}
			db.SetStartTime(startTime)
		} else {
			db.SetStartTime(time.Now().UTC().Add(gs.GraceDuration()))
		}
	}
	start := db.GetStartTime()
	if start == nil {
		log.Panicf("Error fetching start time from database")
	}
	gs.mu.Lock()
	gs.settings.StartTime = start
	gs.mu.Unlock()
}

func syncTeamsFromConfig(c *Config) {
	conn := db.ConnectDB()
	ctx := context.Background()

	existing := make([]db.Team, 0)
	if err := conn.NewSelect().Model(&existing).Scan(ctx); err != nil {
		log.Panicf("Error loading teams: %v", err)
	}
	known := make(map[int]bool, len(existing))
	for _, t := range existing {
		known[t.ID] = true
	}

	configured := make(map[int]bool, len(c.Teams))
	for _, t := range c.Teams {
		configured[t.ID] = true
		if known[t.ID] {
			continue
		}
		token := ""
		if t.Token != nil {
			token = *t.Token
		}
		row := &db.Team{
			ID:        t.ID,
			Name:      t.Name,
			Token:     token,
			Image:     t.Image,
			Nop:       t.Nop,
			Node:      t.Node,
			UpdatedAt: time.Now(),
		}
		if _, err := conn.NewInsert().Model(row).Exec(ctx); err != nil {
			log.Criticalf("Error inserting team %v: %v", t.ID, err)
		}
	}

	// Teams removed from config.json are dropped from the runtime state; their
	// historical rows are kept so the scoreboard of past rounds still resolves.
	for _, t := range existing {
		if !configured[t.ID] {
			if _, err := conn.NewDelete().Model((*db.Team)(nil)).Where("id = ?", t.ID).Exec(ctx); err != nil {
				log.Criticalf("Error deleting team %v: %v", t.ID, err)
			}
		}
	}
}

func discoverServices() []string {
	found := make([]string, 0)
	entries, err := os.ReadDir("../checkers")
	if err != nil {
		log.Errorf("Cannot list checkers directory: %v", err)
		return found
	}
	for _, e := range entries {
		if !e.IsDir() {
			continue
		}
		if _, err := os.Stat("../checkers/" + e.Name() + "/checker.py"); err == nil {
			found = append(found, e.Name())
		}
	}
	sort.Strings(found)
	return found
}

func syncServicesFromDisk() {
	conn := db.ConnectDB()
	ctx := context.Background()

	rows := make([]db.Service, 0)
	if err := conn.NewSelect().Model(&rows).Scan(ctx); err != nil {
		log.Panicf("Error loading services: %v", err)
	}
	known := make(map[string]bool, len(rows))
	for _, s := range rows {
		known[s.Name] = true
	}
	for _, name := range discoverServices() {
		if known[name] {
			continue
		}
		if _, err := conn.NewInsert().Model(&db.Service{
			Name:      name,
			Enabled:   true,
			Weight:    1,
			UpdatedAt: time.Now(),
		}).Exec(ctx); err != nil {
			log.Criticalf("Error inserting service %v: %v", name, err)
		}
	}
}

// ReloadState refreshes the in-memory snapshot from the database.
func ReloadState() {
	conn := db.ConnectDB()
	ctx := context.Background()

	settings := Settings{
		TickTime:            settingInt(setTickTime, 120),
		FlagExpireTicks:     settingInt(setFlagExpireTicks, 5),
		InitialServiceScore: settingFloat(setInitialScore, 5000),
		MaxFlagsPerRequest:  int(settingInt(setMaxFlags, 3000)),
		GraceTime:           settingInt(setGraceTime, 0),
		CheckerTimeout:      settingInt(setCheckerTimeout, 30),
		FlagRegex:           "[A-Z0-9]{31}=",
		EndTime:             settingTime(setEndTime, nil),
		ScoreboardFreezeAt:  settingTime(setFreezeAt, nil),
		ScoreboardFrozen:    settingBool(setFrozen, false),
		ScoreboardFreezeRd:  int(settingInt(setFreezeRound, -1)),
		GamePaused:          settingBool(setGamePaused, false),
		StartTime:           db.GetStartTime(),
	}
	if raw := readSetting(setSubmissionTmo); raw != nil && strings.TrimSpace(*raw) != "" {
		if parsed, err := strconv.ParseFloat(*raw, 64); err == nil {
			settings.SubmissionTimeout = &parsed
		}
	}
	if settings.TickTime <= 0 {
		settings.TickTime = 120
	}

	teamRows := make([]db.Team, 0)
	if err := conn.NewSelect().Model(&teamRows).Order("id ASC").Scan(ctx); err != nil {
		log.Criticalf("Error loading teams: %v", err)
	}
	teams := make([]TeamState, 0, len(teamRows))
	for _, t := range teamRows {
		teams = append(teams, TeamState{
			ID:            t.ID,
			Name:          t.Name,
			Token:         t.Token,
			Image:         t.Image,
			Nop:           t.Nop,
			GameBanned:    t.GameBanned,
			NetworkBanned: t.NetworkBanned,
			BanReason:     t.BanReason,
			Node:          t.Node,
			IP:            teamIDToIP(t.ID),
		})
	}

	present := make(map[string]bool)
	for _, name := range discoverServices() {
		present[name] = true
	}
	serviceRows := make([]db.Service, 0)
	if err := conn.NewSelect().Model(&serviceRows).Order("name ASC").Scan(ctx); err != nil {
		log.Criticalf("Error loading services: %v", err)
	}
	services := make([]ServiceState, 0, len(serviceRows))
	for _, s := range serviceRows {
		services = append(services, ServiceState{
			Name:        s.Name,
			Enabled:     s.Enabled,
			Weight:      s.Weight,
			Description: s.Description,
			Present:     present[s.Name],
		})
	}

	networkState := "unknown"
	if raw := readSetting(setNetworkStateKey); raw != nil && *raw != "" {
		networkState = *raw
	}

	gs.mu.Lock()
	if settings.StartTime == nil {
		settings.StartTime = gs.settings.StartTime
	}
	gs.settings = settings
	gs.teams = teams
	gs.services = services
	gs.networkState = networkState
	gs.suspendedProfiles = map[string]bool{}
	if raw := readSetting(setSuspendedVPNKey); raw != nil && *raw != "" {
		for _, address := range strings.Split(*raw, ",") {
			if address = strings.TrimSpace(address); address != "" {
				gs.suspendedProfiles[address] = true
			}
		}
	}
	gs.mu.Unlock()
}

// ----------------------------------------------------------------------------
// accessors
// ----------------------------------------------------------------------------

func (s *GameState) Settings() Settings {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return s.settings
}

func (s *GameState) Teams() []TeamState {
	s.mu.RLock()
	defer s.mu.RUnlock()
	out := make([]TeamState, len(s.teams))
	copy(out, s.teams)
	return out
}

func (s *GameState) Services() []ServiceState {
	s.mu.RLock()
	defer s.mu.RUnlock()
	out := make([]ServiceState, len(s.services))
	copy(out, s.services)
	return out
}

// ServiceNames returns every known service, including the disabled ones: the
// scoreboard must keep showing a service that was turned off mid-game.
func (s *GameState) ServiceNames() []string {
	s.mu.RLock()
	defer s.mu.RUnlock()
	out := make([]string, 0, len(s.services))
	for _, svc := range s.services {
		out = append(out, svc.Name)
	}
	return out
}

// CheckedServices returns the services the checker loop must run this round.
func (s *GameState) CheckedServices() []string {
	s.mu.RLock()
	defer s.mu.RUnlock()
	out := make([]string, 0, len(s.services))
	for _, svc := range s.services {
		if svc.Enabled && svc.Present {
			out = append(out, svc.Name)
		}
	}
	return out
}

func (s *GameState) ServiceWeight(name string) float64 {
	s.mu.RLock()
	defer s.mu.RUnlock()
	for _, svc := range s.services {
		if svc.Name == name {
			if svc.Weight <= 0 {
				return 1
			}
			return svc.Weight
		}
	}
	return 1
}

func (s *GameState) TeamByID(id int) *TeamState {
	s.mu.RLock()
	defer s.mu.RUnlock()
	for i := range s.teams {
		if s.teams[i].ID == id {
			team := s.teams[i]
			return &team
		}
	}
	return nil
}

func (s *GameState) TeamByToken(token string) *TeamState {
	if token == "" {
		return nil
	}
	s.mu.RLock()
	defer s.mu.RUnlock()
	for i := range s.teams {
		if s.teams[i].Token == token {
			team := s.teams[i]
			return &team
		}
	}
	return nil
}

func (s *GameState) TeamByIP(ip string) *TeamState {
	return s.TeamByID(extractTeamID(ip))
}

func (s *GameState) RoundLen() time.Duration {
	return time.Duration(s.Settings().TickTime) * time.Second
}

func (s *GameState) GraceDuration() time.Duration {
	return time.Duration(s.Settings().GraceTime) * time.Second
}

func (s *GameState) CheckerTimeout() time.Duration {
	return time.Duration(s.Settings().CheckerTimeout) * time.Second
}

func (s *GameState) StartTime() time.Time {
	st := s.Settings().StartTime
	if st == nil {
		return time.Now()
	}
	return *st
}

func (s *GameState) EndTime() *time.Time {
	return s.Settings().EndTime
}

func (s *GameState) GameEnded() bool {
	end := s.EndTime()
	return end != nil && time.Now().After(*end)
}

func (s *GameState) NetworkState() string {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return s.networkState
}

// SuspendedProfiles are the VPN profiles that must stay cut off, sorted so the
// answer is stable between calls.
func (s *GameState) SuspendedProfiles() []string {
	s.mu.RLock()
	defer s.mu.RUnlock()
	out := make([]string, 0, len(s.suspendedProfiles))
	for address := range s.suspendedProfiles {
		out = append(out, address)
	}
	sort.Strings(out)
	return out
}

func (s *GameState) IsProfileSuspended(address string) bool {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return s.suspendedProfiles[address]
}

// SetProfileSuspended cuts one VPN profile off the game network, or lets it
// back in. Only that profile is touched: the rest of its team keeps playing.
func (s *GameState) SetProfileSuspended(address string, suspended bool) {
	s.mu.Lock()
	if suspended {
		s.suspendedProfiles[address] = true
	} else {
		delete(s.suspendedProfiles, address)
	}
	addresses := make([]string, 0, len(s.suspendedProfiles))
	for entry := range s.suspendedProfiles {
		addresses = append(addresses, entry)
	}
	s.mu.Unlock()
	sort.Strings(addresses)
	writeSetting(setSuspendedVPNKey, strings.Join(addresses, ","))
}

// setNetworkState records the state the game network is *supposed* to be in.
// It is persisted because it is the only thing that can tell a router which
// just restarted whether the game is running: a router always comes up frozen.
func (s *GameState) setNetworkState(state string) {
	writeSetting(setNetworkStateKey, state)
	s.mu.Lock()
	s.networkState = state
	s.mu.Unlock()
	// The players are told the network state through /api/status, which is
	// cached per round: without this the banner would lag a whole round behind
	// a lock the organizers just applied.
	statusCache.invalidate()
}

// ----------------------------------------------------------------------------
// mutators (admin panel)
// ----------------------------------------------------------------------------

func (s *GameState) SetScoreboardFreeze(frozen bool, round int) {
	writeSetting(setFrozen, boolToSetting(frozen))
	writeSetting(setFreezeRound, strconv.Itoa(round))
	s.mu.Lock()
	s.settings.ScoreboardFrozen = frozen
	s.settings.ScoreboardFreezeRd = round
	s.mu.Unlock()
	invalidateAllCaches()
}

func (s *GameState) SetScoreboardFreezeAt(at *time.Time) {
	writeSetting(setFreezeAt, timeToSetting(at))
	s.mu.Lock()
	s.settings.ScoreboardFreezeAt = at
	s.mu.Unlock()
	_ = patchConfigFile(map[string]interface{}{
		"scoreboard_freeze_time": nullableTimeJSON(at),
	})
}

func nullableTimeJSON(t *time.Time) interface{} {
	if t == nil {
		return nil
	}
	return t.Format(time.RFC3339)
}

func (s *GameState) SetGamePaused(paused bool) {
	writeSetting(setGamePaused, boolToSetting(paused))
	s.mu.Lock()
	s.settings.GamePaused = paused
	s.mu.Unlock()
}

// EffectiveScoreboardRound is the round whose ranking must be served: the
// freeze round while the scoreboard is frozen, the live one otherwise.
func (s *GameState) EffectiveScoreboardRound(currentRound int) int {
	st := s.Settings()
	if st.ScoreboardFrozen && st.ScoreboardFreezeRd >= 0 && st.ScoreboardFreezeRd < currentRound {
		return st.ScoreboardFreezeRd
	}
	return currentRound
}

// initScoreboard makes sure every (team, service) pair has a score row. It is
// idempotent so it can also run after a team or a service is added at runtime.
func initScoreboard() {
	ctx := context.Background()
	dbc := db.ConnectDB()
	log.Debugf("Initializing scoreboard")

	initial := gs.Settings().InitialServiceScore
	for _, team := range gs.Teams() {
		for _, service := range gs.ServiceNames() {
			exists, err := dbc.NewSelect().Model((*db.ServiceScore)(nil)).
				Where("team = ? and service = ?", team.IP, service).Exists(ctx)
			if err != nil {
				log.Criticalf("Error fetching service score: %v", err)
				continue
			}
			if exists {
				continue
			}
			if _, err := dbc.NewInsert().Model(&db.ServiceScore{
				Team:    team.IP,
				Service: service,
				Score:   initial,
				Offense: 0.0,
				Defense: 0.0,
			}).Exec(ctx); err != nil {
				log.Criticalf("Error inserting service score: %v", err)
			}
		}
	}
}

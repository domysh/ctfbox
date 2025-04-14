package main

import (
	"context"
	"encoding/json"
	"game/db"
	"game/log"
	"net/http"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"time"

	"github.com/gorilla/mux"
	"github.com/rs/cors"
)

type ServiceRoundStatus struct {
	Service         string  `json:"service"`
	StolenFlags     uint    `json:"stolen_flags"`
	OffensivePoints float64 `json:"offensive_points"`
	DefensePoints   float64 `json:"defensive_points"`
	LostFlags       uint    `json:"lost_flags"`
	Sla             float64 `json:"sla"`
	Score           float64 `json:"score"`
	TicksUp         uint    `json:"ticks_up"`
	TicksDown       uint    `json:"ticks_down"`
	PutFlag         int     `json:"put_flag"`
	PutFlagMsg      string  `json:"put_flag_msg"`
	GetFlag         int     `json:"get_flag"`
	GetFlagMsg      string  `json:"get_flag_msg"`
	SlaCheck        int     `json:"sla_check"`
	SlaCheckMsg     string  `json:"sla_check_msg"`
	FinalScore      float64 `json:"final_score"`
}

type TeamRoundStatusShort struct {
	Team  string  `json:"team"`
	Score float64 `json:"score"`
}

type ChartAPIResponse struct {
	Round  uint                   `json:"round"`
	Scores []TeamRoundStatusShort `json:"scores"`
}

func handleChart(w http.ResponseWriter, r *http.Request) {
	round := db.GetExposedRound()
	if round < 0 {
		if err := json.NewEncoder(w).Encode([]ChartAPIResponse{}); err != nil {
			log.Errorf("Error encoding response: %v", err)
			http.Error(w, "Internal server error", http.StatusInternalServerError)
			return
		}
		return
	}
	response := make([]ChartAPIResponse, round+1)
	dbScores := new([]db.StatusHistory)
	ctx := context.Background()
	for i := 0; i <= int(round); i++ {
		if err := conn.NewSelect().Model(dbScores).Where("round = ?", i).Scan(ctx); err != nil {
			log.Errorf("Error fetching scores for round %d: %v", i, err)
			http.Error(w, "Internal server error", http.StatusInternalServerError)
			return
		}
		scores := make([]TeamRoundStatusShort, 0, len(conf.Teams))
		for _, score := range *dbScores {
			scoresTeamIndex := -1
			for j, team := range scores {
				if team.Team == score.Team {
					scoresTeamIndex = j
					break
				}
			}
			if scoresTeamIndex != -1 {
				scores[scoresTeamIndex].Score += score.Score * score.Sla
			} else {
				scores = append(scores, TeamRoundStatusShort{
					Team:  score.Team,
					Score: score.Score * score.Sla,
				})
			}
		}
		response[i] = ChartAPIResponse{
			Round:  uint(i),
			Scores: scores,
		}
	}
	w.Header().Set("Content-Type", "application/json")
	if err := json.NewEncoder(w).Encode(response); err != nil {
		log.Errorf("Error encoding response: %v", err)
		http.Error(w, "Internal server error", http.StatusInternalServerError)
		return
	}

}

type TeamRoundStatus struct {
	Team     string               `json:"team"`
	Score    float64              `json:"score"`
	Services []ServiceRoundStatus `json:"services"`
}

type ScoreboardAPIResponse struct {
	Round  uint              `json:"round"`
	Scores []TeamRoundStatus `json:"scores"`
}

func handleScoreboard(w http.ResponseWriter, r *http.Request) {

	round := db.GetExposedRound()

	if round < 0 {
		if err := json.NewEncoder(w).Encode(ScoreboardAPIResponse{
			Round:  0,
			Scores: make([]TeamRoundStatus, 0),
		}); err != nil {
			log.Errorf("Error encoding response: %v", err)
			http.Error(w, "Internal server error", http.StatusInternalServerError)
			return
		}
		return
	}

	response := ScoreboardAPIResponse{
		Round:  uint(round),
		Scores: make([]TeamRoundStatus, 0, len(conf.Teams)),
	}

	ctx := context.Background()
	for _, teamInfo := range conf.Teams {
		team := teamIDToIP(teamInfo.ID)
		scoreData := new([]db.StatusHistory)
		if err := conn.NewSelect().Model(scoreData).Where("team = ? and round = ?", team, round).Scan(ctx); err != nil {
			log.Errorf("Error fetching scores for team %s: %v", team, err)
			http.Error(w, "Internal server error", http.StatusInternalServerError)
			return
		}
		services := make([]ServiceRoundStatus, 0, len(conf.Services))
		totScore := 0.0
		for _, service := range *scoreData {
			services = append(services, ServiceRoundStatus{
				Service:         service.Service,
				StolenFlags:     service.StolenFlags,
				OffensivePoints: service.OffensePoints,
				DefensePoints:   service.DefensePoints,
				LostFlags:       service.LostFlags,
				Sla:             service.Sla,
				Score:           service.Score,
				TicksUp:         service.SlaUpTimes,
				TicksDown:       service.SlaTotTimes - service.SlaUpTimes,
				PutFlag:         service.PutFlagStatus,
				PutFlagMsg:      service.PutFlagMessage,
				GetFlag:         service.GetFlagStatus,
				GetFlagMsg:      service.GetFlagMessage,
				SlaCheck:        service.CheckStatus,
				SlaCheckMsg:     service.CheckMessage,
				FinalScore:      service.Score * service.Sla,
			})
			totScore += service.Score * service.Sla
		}
		response.Scores = append(response.Scores, TeamRoundStatus{
			Team:     team,
			Score:    totScore,
			Services: services,
		})
	}
	w.Header().Set("Content-Type", "application/json")
	if err := json.NewEncoder(w).Encode(response); err != nil {
		log.Errorf("Error encoding response: %v", err)
		http.Error(w, "Internal server error", http.StatusInternalServerError)
		return
	}

}

type TeamAPIResponse struct {
	Round uint            `json:"round"`
	Score TeamRoundStatus `json:"score"`
}

func handleTeam(w http.ResponseWriter, r *http.Request) {
	teamId, err := strconv.Atoi(mux.Vars(r)["team_id"])
	if err != nil {
		http.Error(w, "Invalid team ID", http.StatusBadRequest)
		log.Errorf("Error: invalid team ID %v", mux.Vars(r)["team_id"])
		return
	}
	teamInfo := conf.getTeamByID(teamId)
	if teamInfo == nil {
		http.Error(w, "Invalid team ID", http.StatusBadRequest)
		log.Errorf("Error: invalid team ID %v", mux.Vars(r)["team_id"])
		return
	}
	round := db.GetExposedRound()
	if round < 0 {
		if err := json.NewEncoder(w).Encode([]TeamAPIResponse{}); err != nil {
			log.Errorf("Error encoding response: %v", err)
			http.Error(w, "Internal server error", http.StatusInternalServerError)
			return
		}
	}

	team := teamIDToIP(teamInfo.ID)
	response := make([]TeamAPIResponse, round+1)
	ctx := context.Background()
	for i := 0; i <= int(round); i++ {
		scoreData := new([]db.StatusHistory)
		if err := conn.NewSelect().Model(scoreData).Where("team = ? and round = ?", team, i).Scan(ctx); err != nil {
			log.Errorf("Error fetching scores for team %s: %v", team, err)
			http.Error(w, "Internal server error", http.StatusInternalServerError)
			return
		}
		services := make([]ServiceRoundStatus, 0, len(conf.Services))
		totalScore := 0.0
		for _, service := range *scoreData {
			services = append(services, ServiceRoundStatus{
				Service:         service.Service,
				StolenFlags:     service.StolenFlags,
				OffensivePoints: service.OffensePoints,
				DefensePoints:   service.DefensePoints,
				LostFlags:       service.LostFlags,
				Sla:             service.Sla,
				Score:           service.Score,
				TicksUp:         service.SlaUpTimes,
				TicksDown:       service.SlaTotTimes - service.SlaUpTimes,
				PutFlag:         service.PutFlagStatus,
				PutFlagMsg:      service.PutFlagMessage,
				GetFlag:         service.GetFlagStatus,
				GetFlagMsg:      service.GetFlagMessage,
				SlaCheck:        service.CheckStatus,
				SlaCheckMsg:     service.CheckMessage,
				FinalScore:      service.Score * service.Sla,
			})
			totalScore += service.Score * service.Sla
		}
		response[i] = TeamAPIResponse{
			Round: uint(i),
			Score: TeamRoundStatus{
				Team:     team,
				Score:    totalScore,
				Services: services,
			},
		}

	}

	w.Header().Set("Content-Type", "application/json")
	if err := json.NewEncoder(w).Encode(response); err != nil {
		log.Errorf("Error encoding response: %v", err)
		http.Error(w, "Internal server error", http.StatusInternalServerError)
		return
	}

}

type TeamStatus struct {
	Id        int    `json:"id"`
	Name      string `json:"name"`
	ShortName string `json:"shortname"`
	Host      string `json:"host"`
	Image     string `json:"image"`
	Nop       bool   `json:"nop"`
}

type ServiceStatus struct {
	Name string `json:"name"`
}

type StatusAPIResponse struct {
	Teams               []TeamStatus    `json:"teams"`
	Services            []ServiceStatus `json:"services"`
	StartTime           string          `json:"start"`
	EndTime             *string         `json:"end"`
	RoundLen            uint            `json:"roundTime"`
	FlagExpireTicks     uint            `json:"flag_expire_ticks"`
	SubmitterFlagsLimit uint            `json:"submitter_flags_limit"`
	SubmitterRateLimit  uint            `json:"submitter_rate_limit"`
	CurrentRound        int             `json:"current_round"`
	FlagRegex           string          `json:"flag_regex"`
	InitServicePoints   float64         `json:"init_service_points"`
}

func handleStatus(w http.ResponseWriter, r *http.Request) {
	teams := make([]TeamStatus, 0, len(conf.Teams))
	for _, team := range conf.Teams {
		teams = append(teams, TeamStatus{
			Id:        team.ID,
			Name:      team.Name,
			Host:      teamIDToIP(team.ID),
			ShortName: strings.ToLower(strings.ReplaceAll(team.Name, " ", "_")),
			Image:     team.Image,
			Nop:       team.Nop,
		})
	}

	var endTime *string = nil
	if conf.GameEndTime != nil {
		endTimeStr := conf.GameEndTime.Format(time.RFC3339)
		endTime = &endTimeStr
	}

	w.Header().Set("Content-Type", "application/json")
	services := make([]ServiceStatus, 0, len(conf.Services))
	for _, service := range conf.Services {
		services = append(services, ServiceStatus{Name: service})
	}
	if err := json.NewEncoder(w).Encode(StatusAPIResponse{
		Teams:               teams,
		Services:            services,
		StartTime:           conf.GameStartTime.Format(time.RFC3339),
		EndTime:             endTime,
		RoundLen:            uint(conf.RoundLen / time.Second),
		FlagExpireTicks:     uint(conf.FlagExpireTicks),
		SubmitterFlagsLimit: uint(conf.MaxFlagsPerRequest),
		SubmitterRateLimit:  uint(*conf.SubmitterTimeout),
		CurrentRound:        db.GetExposedRound(),
		FlagRegex:           conf.FlagRegex,
		InitServicePoints:   conf.InitialServiceScore,
	}); err != nil {
		log.Errorf("Error encoding response: %v", err)
		http.Error(w, "Internal server error", http.StatusInternalServerError)
		return
	}
}

type spaHandler struct {
	staticPath string
	indexPath  string
}

func (h spaHandler) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	// Join internally call path.Clean to prevent directory traversal
	path := filepath.Join(h.staticPath, r.URL.Path)

	// check whether a file exists or is a directory at the given path
	fi, err := os.Stat(path)
	if os.IsNotExist(err) || fi.IsDir() {
		// file does not exist or path is a directory, serve index.html
		http.ServeFile(w, r, filepath.Join(h.staticPath, h.indexPath))
		return
	}

	if err != nil {
		// if we got an error (that wasn't that the file doesn't exist) stating the
		// file, return a 500 internal server error and stop
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}

	// otherwise, use http.FileServer to serve the static file
	http.FileServer(http.Dir(h.staticPath)).ServeHTTP(w, r)
}

func serveScoreboard() {
	router := mux.NewRouter()

	router.HandleFunc("/api/scoreboard", handleScoreboard).Methods("GET")
	router.HandleFunc("/api/chart", handleChart).Methods("GET")
	router.HandleFunc("/api/team/{team_id}", handleTeam).Methods("GET")
	router.HandleFunc("/api/status", handleStatus).Methods("GET")

	log.Noticef("Starting flag_ids server on :80")
	spa := spaHandler{staticPath: "frontend", indexPath: "index.html"}
	router.PathPrefix("/").Handler(spa)

	var finalHandler http.Handler = router

	if conf.Debug {
		corsPolicy := cors.New(cors.Options{
			AllowedOrigins:   []string{"*"},
			AllowCredentials: true,
		})
		finalHandler = corsPolicy.Handler(router)
	}

	srv := &http.Server{
		Handler:      finalHandler,
		Addr:         "0.0.0.0:80",
		WriteTimeout: 30 * time.Second,
		ReadTimeout:  30 * time.Second,
	}

	log.Fatal(srv.ListenAndServe())

}

package main

import (
	"context"
	"encoding/json"
	"fmt"
	"game/db"
	"game/log"
	"net/http"
	"strconv"
	"time"

	"github.com/gorilla/mux"
)

type FlagIDSub struct {
	Token     string      `json:"token"`
	ServiceID string      `json:"serviceId"`
	TeamID    string      `json:"teamId"`
	Round     int         `json:"round"`
	FlagID    interface{} `json:"flagId"`
}

//Needed to save on postgres also string, numbers ecc... that are not directly supported by jsonb type

func submitFlagID(w http.ResponseWriter, r *http.Request) {
	var ctx context.Context = context.Background()
	jsonDecoder := json.NewDecoder(r.Body)
	var sub FlagIDSub
	if err := jsonDecoder.Decode(&sub); err != nil {
		http.Error(w, "Invalid request", http.StatusBadRequest)
		log.Errorf("Error decoding flag_id: %v", err)
		return
	}

	if sub.Token != conf.Token || sub.ServiceID == "" || sub.TeamID == "" || sub.FlagID == "" {
		http.Error(w, "Invalid request", http.StatusBadRequest)
		log.Errorf("Error: invalid flag_id submission: %+v", sub)
		return
	}

	teamId, err := strconv.Atoi(sub.TeamID)
	if err != nil {
		teamId = extractTeamID(sub.TeamID)
	}
	teamInfo := conf.getTeamByID(teamId)
	if teamInfo == nil {
		http.Error(w, "Invalid request", http.StatusBadRequest)
		log.Errorf("Error: invalid team id %v", sub.TeamID)
		return
	}
	team := teamIDToIP(teamInfo.ID)

	var associatedFlag = new(db.Flag)
	if err := conn.NewSelect().Model(associatedFlag).Where("team = ? and round = ? and service = ?", team, sub.Round, sub.ServiceID).Scan(ctx); err != nil {
		http.Error(w, "Invalid request", http.StatusBadRequest)
		log.Errorf("Error: invalid flag_id submission: %v", err)
		return
	}

	if _, err := conn.NewUpdate().Model(associatedFlag).Set("external_flag_id = ?", db.FlagIdWrapper{K: sub.FlagID}).WherePK().Exec(ctx); err != nil {
		http.Error(w, "Internal server error", http.StatusInternalServerError)
		log.Criticalf("Error updating flag_id: %v", err)
		return
	}

	log.Debugf("Received flag_id %v from %v:%v (%v) in round %v",
		sub.FlagID, sub.TeamID, team, sub.ServiceID, sub.Round)
}

func retriveFlagIDs(w http.ResponseWriter, r *http.Request) {
	var ctx context.Context = context.Background()
	currentRound := db.GetExposedRound()
	query := r.URL.Query()

	enc := json.NewEncoder(w)

	services, ok_service := query["service"]
	if ok_service {
		if len(services) < 1 {
			ok_service = false
		} else {
			found := false
			for _, s := range conf.Services {
				if services[0] == s {
					found = true
					break
				}
			}
			if !found {
				http.Error(w, "Invalid request", http.StatusBadRequest)
				log.Errorf("Error: invalid service %v", services[0])
				return
			}
		}
	}

	teamList, ok_team := query["team"]
	teamId := 0
	if ok_team {
		if len(teamList) == 1 {
			teamParsedId, err := strconv.Atoi(teamList[0])
			teamId = teamParsedId
			if err != nil {
				http.Error(w, "Invalid request", http.StatusBadRequest)
				log.Errorf("Error: invalid team id %v", teamList[0])
				return
			}
			teamExists := false
			for _, t := range conf.Teams {
				if teamId == t.ID {
					teamExists = true
					break
				}
			}
			if !teamExists {
				http.Error(w, "Invalid request", http.StatusBadRequest)
				log.Errorf("Error: invalid team id %v", teamId)
				return
			}
		} else {
			ok_team = false
		}
	}
	team := teamIDToIP(teamId)
	roundList, ok_round := query["round"]
	var round *uint = nil
	if ok_round {
		if len(roundList) == 1 {
			parsedRound, err := strconv.Atoi(roundList[0])
			if err != nil {
				http.Error(w, "Invalid request", http.StatusBadRequest)
				log.Errorf("Error: invalid round %v", roundList[0])
				return
			}
			round = new(uint)
			*round = uint(parsedRound)
		}
	}

	validFlags := make([]db.Flag, 0)
	var err error = nil
	if !ok_service && !ok_team {
		err = conn.NewSelect().Model(&validFlags).Where("? - round < ? and round <= ?", currentRound, conf.FlagExpireTicks, currentRound).Scan(ctx)
	} else if !ok_service {
		err = conn.NewSelect().Model(&validFlags).Where("team = ? and ? - round < ? and round <= ?", team, currentRound, conf.FlagExpireTicks, currentRound).Scan(ctx)
	} else if !ok_team {
		err = conn.NewSelect().Model(&validFlags).Where("service = ? and ? - round < ? and round <= ?", services[0], currentRound, conf.FlagExpireTicks, currentRound).Scan(ctx)
	} else {
		err = conn.NewSelect().Model(&validFlags).Where("team = ? and service = ? and ? - round < ? and round <= ?", team, services[0], currentRound, conf.FlagExpireTicks, currentRound).Scan(ctx)
	}

	if err != nil {
		http.Error(w, "Internal server error", http.StatusInternalServerError)
		log.Errorf("Error fetching flag_ids: %v", err)
		return
	}

	flagIDs := make(map[string]map[string]map[string]interface{})
	for _, flag := range validFlags {
		if round != nil && flag.Round != *round {
			continue
		}
		if flag.ExternalFlagId.K == nil {
			continue
		}
		if _, ok := flagIDs[flag.Service]; !ok {
			flagIDs[flag.Service] = make(map[string]map[string]interface{})
		}
		flagTeamId := fmt.Sprintf("%d", extractTeamID(flag.Team))
		if _, ok := flagIDs[flag.Service][flagTeamId]; !ok {
			flagIDs[flag.Service][flagTeamId] = make(map[string]interface{}, 0)
		}

		flagIDs[flag.Service][flagTeamId][fmt.Sprintf("%d", flag.Round)] = flag.ExternalFlagId.K
	}

	w.Header().Set("Content-Type", "application/json")
	if err := enc.Encode(flagIDs); err != nil {
		http.Error(w, "Internal server error", http.StatusInternalServerError)
		log.Errorf("Error encoding flag_ids: %v", err)
		return
	}

	log.Debugf("Received flag_ids request %v", query)
}

func serveFlagIDs() {
	router := mux.NewRouter()

	router.HandleFunc("/postFlagId", submitFlagID).Methods("POST")
	router.HandleFunc("/flagIds", retriveFlagIDs).Methods("GET")

	log.Noticef("Starting flag_ids server on :8081")

	srv := &http.Server{
		Handler:      router,
		Addr:         "0.0.0.0:8081",
		WriteTimeout: 30 * time.Second,
		ReadTimeout:  30 * time.Second,
	}

	log.Fatal(srv.ListenAndServe())
}

package main

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"game/db"
	"game/log"
	"net/http"
	"strconv"
	"sync"
	"time"

	"github.com/gorilla/mux"
)

// Struttura per la cache completa dei flag ID
var (
	// Mantiene la cache completa come struttura dati
	flagIDsCompleteCache struct {
		sync.RWMutex
		data      map[string]map[string]map[string]interface{} // struttura dati in memoria
		jsonData  []byte                                       // rappresentazione JSON per risposta rapida
		timestamp time.Time                                    // per tracciare l'ultimo aggiornamento
	}

	// Cache per risposte filtrate già generate
	flagIDsFilteredCache struct {
		sync.RWMutex
		cache map[string][]byte
	}
)

// Funzione per inizializzare le cache
func init() {
	flagIDsCompleteCache.data = make(map[string]map[string]map[string]interface{})
	flagIDsFilteredCache.cache = make(map[string][]byte)
}

// Funzione per generare la chiave di cache basata sui parametri di query
func getFlagIDsCacheKey(service, team string, round *uint) string {
	if round == nil {
		return fmt.Sprintf("%s:%s:nil", service, team)
	}
	return fmt.Sprintf("%s:%s:%d", service, team, *round)
}

// Funzione per invalidare la cache dei flag IDs
func invalidateFlagIDsCache() {
	// Azzera la cache completa
	flagIDsCompleteCache.Lock()
	flagIDsCompleteCache.data = make(map[string]map[string]map[string]interface{})
	flagIDsCompleteCache.jsonData = nil
	flagIDsCompleteCache.Unlock()

	// Azzera la cache filtrata
	flagIDsFilteredCache.Lock()
	flagIDsFilteredCache.cache = make(map[string][]byte)
	flagIDsFilteredCache.Unlock()

	log.Debugf("Flag IDs cache invalidated")
}

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

	// Invalida la cache quando viene aggiunto un nuovo flag ID
	invalidateFlagIDsCache()

	log.Debugf("Received flag_id %v from %v:%v (%v) in round %v",
		sub.FlagID, sub.TeamID, team, sub.ServiceID, sub.Round)
}

// Funzione per ottenere o aggiornare la cache completa
func getOrUpdateCompleteCache(ctx context.Context, currentRound int) (map[string]map[string]map[string]interface{}, []byte, error) {
	flagIDsCompleteCache.RLock()
	// Verifica se la cache è già popolata
	if flagIDsCompleteCache.jsonData != nil {
		data := flagIDsCompleteCache.data
		jsonData := flagIDsCompleteCache.jsonData
		flagIDsCompleteCache.RUnlock()
		return data, jsonData, nil
	}
	flagIDsCompleteCache.RUnlock()

	// Dobbiamo ricostruire la cache
	flagIDsCompleteCache.Lock()
	defer flagIDsCompleteCache.Unlock()

	// Controlla nuovamente dopo aver ottenuto il lock esclusivo
	if flagIDsCompleteCache.jsonData != nil {
		return flagIDsCompleteCache.data, flagIDsCompleteCache.jsonData, nil
	}

	// Recupera tutti i flag validi dal database
	validFlags := make([]db.Flag, 0)
	if err := conn.NewSelect().Model(&validFlags).Where("? - round < ? and round <= ?", currentRound, conf.FlagExpireTicks, currentRound).Scan(ctx); err != nil {
		return nil, nil, err
	}

	// Costruisci la struttura dati in memoria
	flagIDs := make(map[string]map[string]map[string]interface{})
	for _, flag := range validFlags {
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

	// Genera la rappresentazione JSON
	var responseBuffer bytes.Buffer
	enc := json.NewEncoder(&responseBuffer)
	if err := enc.Encode(flagIDs); err != nil {
		return nil, nil, err
	}

	// Aggiorna la cache
	flagIDsCompleteCache.data = flagIDs
	flagIDsCompleteCache.jsonData = responseBuffer.Bytes()
	flagIDsCompleteCache.timestamp = time.Now()

	return flagIDs, flagIDsCompleteCache.jsonData, nil
}

// Funzione per filtrare i dati dalla cache completa
func filterCacheData(completeData map[string]map[string]map[string]interface{},
	serviceFilter string, teamFilter string, roundFilter *uint) map[string]map[string]map[string]interface{} {

	result := make(map[string]map[string]map[string]interface{})

	// Filtra per servizio se specificato
	if serviceFilter != "" {
		if serviceData, ok := completeData[serviceFilter]; ok {
			result[serviceFilter] = make(map[string]map[string]interface{})

			// Filtra per team se specificato
			if teamFilter != "" {
				teamID := fmt.Sprintf("%d", extractTeamID(teamFilter))
				if teamData, ok := serviceData[teamID]; ok {
					result[serviceFilter][teamID] = make(map[string]interface{})

					// Filtra per round se specificato
					if roundFilter != nil {
						roundStr := fmt.Sprintf("%d", *roundFilter)
						if flagValue, ok := teamData[roundStr]; ok {
							result[serviceFilter][teamID][roundStr] = flagValue
						}
					} else {
						// Copia tutti i round
						for round, flagValue := range teamData {
							result[serviceFilter][teamID][round] = flagValue
						}
					}
				}
			} else {
				// Nessun filtro team, copia tutti i team per questo servizio
				for teamID, teamData := range serviceData {
					result[serviceFilter][teamID] = make(map[string]interface{})

					// Filtra per round se specificato
					if roundFilter != nil {
						roundStr := fmt.Sprintf("%d", *roundFilter)
						if flagValue, ok := teamData[roundStr]; ok {
							result[serviceFilter][teamID][roundStr] = flagValue
						}
					} else {
						// Copia tutti i round
						for round, flagValue := range teamData {
							result[serviceFilter][teamID][round] = flagValue
						}
					}
				}
			}
		}
	} else if teamFilter != "" {
		// Filtro solo per team
		teamID := fmt.Sprintf("%d", extractTeamID(teamFilter))

		// Cerca in tutti i servizi
		for serviceName, serviceData := range completeData {
			if teamData, ok := serviceData[teamID]; ok {
				if _, ok := result[serviceName]; !ok {
					result[serviceName] = make(map[string]map[string]interface{})
				}
				result[serviceName][teamID] = make(map[string]interface{})

				// Filtra per round se specificato
				if roundFilter != nil {
					roundStr := fmt.Sprintf("%d", *roundFilter)
					if flagValue, ok := teamData[roundStr]; ok {
						result[serviceName][teamID][roundStr] = flagValue
					}
				} else {
					// Copia tutti i round
					for round, flagValue := range teamData {
						result[serviceName][teamID][round] = flagValue
					}
				}
			}
		}
	} else if roundFilter != nil {
		// Filtro solo per round
		roundStr := fmt.Sprintf("%d", *roundFilter)

		// Cerca in tutti i servizi e team
		for serviceName, serviceData := range completeData {
			for teamID, teamData := range serviceData {
				if flagValue, ok := teamData[roundStr]; ok {
					if _, ok := result[serviceName]; !ok {
						result[serviceName] = make(map[string]map[string]interface{})
					}
					if _, ok := result[serviceName][teamID]; !ok {
						result[serviceName][teamID] = make(map[string]interface{})
					}
					result[serviceName][teamID][roundStr] = flagValue
				}
			}
		}
	} else {
		// Nessun filtro, ritorna tutto
		return completeData
	}

	return result
}

func retriveFlagIDs(w http.ResponseWriter, r *http.Request) {
	var ctx context.Context = context.Background()
	currentRound := db.GetExposedRound()
	query := r.URL.Query()

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

	// Genero la chiave di cache per la risposta filtrata
	serviceKey := ""
	if ok_service {
		serviceKey = services[0]
	}
	teamKey := ""
	if ok_team {
		teamKey = team
	}
	cacheKey := getFlagIDsCacheKey(serviceKey, teamKey, round)

	// Controllo se ho la risposta già filtrata in cache
	flagIDsFilteredCache.RLock()
	cachedResponse, found := flagIDsFilteredCache.cache[cacheKey]
	flagIDsFilteredCache.RUnlock()

	if found {
		w.Header().Set("Content-Type", "application/json")
		w.Write(cachedResponse)
		log.Debugf("Serving flag_ids request from filtered cache %v", query)
		return
	}

	// Ottieni o aggiorna la cache completa
	completeData, completeJSON, err := getOrUpdateCompleteCache(ctx, currentRound)
	if err != nil {
		http.Error(w, "Internal server error", http.StatusInternalServerError)
		log.Errorf("Error fetching flag_ids: %v", err)
		return
	}

	// Se non ci sono filtri, servi la cache completa
	if !ok_service && !ok_team && round == nil {
		w.Header().Set("Content-Type", "application/json")
		w.Write(completeJSON)
		log.Debugf("Serving flag_ids request from complete cache %v", query)
		return
	}

	// Applica i filtri ai dati in cache
	filteredData := filterCacheData(completeData, serviceKey, teamKey, round)

	// Serializza i dati filtrati
	var responseBuffer bytes.Buffer
	enc := json.NewEncoder(&responseBuffer)
	if err := enc.Encode(filteredData); err != nil {
		http.Error(w, "Internal server error", http.StatusInternalServerError)
		log.Errorf("Error encoding filtered flag_ids: %v", err)
		return
	}

	// Salva i dati filtrati in cache
	responseBytes := responseBuffer.Bytes()
	flagIDsFilteredCache.Lock()
	flagIDsFilteredCache.cache[cacheKey] = responseBytes
	flagIDsFilteredCache.Unlock()

	// Invia la risposta
	w.Header().Set("Content-Type", "application/json")
	w.Write(responseBytes)
	log.Debugf("Serving flag_ids request from newly filtered cache %v", query)
}

func serveFlagIDs() {
	router := mux.NewRouter()

	router.HandleFunc("/postFlagId", submitFlagID).Methods("POST")
	router.HandleFunc("/flagIds", retriveFlagIDs).Methods("GET")

	log.Noticef("Starting flag_ids server on :8081")

	// Applica middleware di compressione
	compressedRouter := compressMiddleware(router)

	srv := &http.Server{
		Handler:      compressedRouter,
		Addr:         "0.0.0.0:8081",
		WriteTimeout: 30 * time.Second,
		ReadTimeout:  30 * time.Second,
	}

	log.Fatal(srv.ListenAndServe())
}

package main

import (
	"context"
	"crypto/subtle"
	"encoding/json"
	"net/http"
	"sort"
	"sync"
	"time"

	"game/db"
	"game/log"

	"github.com/gorilla/mux"
)

// WorkerRegistration is what a worker declares when it joins the cluster.
type WorkerRegistration struct {
	ID       string `json:"id"`
	Name     string `json:"name"`
	Address  string `json:"address"`
	Capacity int    `json:"capacity"`
	Embedded bool   `json:"embedded"`
	Version  string `json:"version"`
}

type WorkerView struct {
	WorkerRegistration
	Running   int       `json:"running"`
	Completed int64     `json:"completed"`
	Failed    int64     `json:"failed"`
	LastSeen  time.Time `json:"last_seen"`
	Alive     bool      `json:"alive"`
}

type workerEntry struct {
	reg       WorkerRegistration
	running   int
	completed int64
	failed    int64
	lastSeen  time.Time
}

type WorkerRegistry struct {
	mu      sync.RWMutex
	workers map[string]*workerEntry
	counter int
}

var registry = &WorkerRegistry{workers: make(map[string]*workerEntry)}

const workerStaleAfter = 30 * time.Second

func (r *WorkerRegistry) Register(reg *WorkerRegistration) string {
	r.mu.Lock()
	defer r.mu.Unlock()
	if reg.ID == "" {
		r.counter++
		reg.ID = "w" + time.Now().Format("150405") + "-" + itoa(r.counter)
	}
	// A worker that restarts says hello with a fresh id; without this the
	// panel would slowly fill up with the ghosts of its previous lives.
	for id, existing := range r.workers {
		if id != reg.ID && existing.reg.Name == reg.Name {
			delete(r.workers, id)
		}
	}
	entry, ok := r.workers[reg.ID]
	if !ok {
		entry = &workerEntry{}
		r.workers[reg.ID] = entry
	}
	entry.reg = *reg
	entry.lastSeen = time.Now()
	return reg.ID
}

func itoa(v int) string {
	if v == 0 {
		return "0"
	}
	digits := ""
	for v > 0 {
		digits = string(rune('0'+v%10)) + digits
		v /= 10
	}
	return digits
}

func (r *WorkerRegistry) SetRunning(id string, running int) {
	r.mu.Lock()
	defer r.mu.Unlock()
	if entry, ok := r.workers[id]; ok {
		entry.running = running
		entry.lastSeen = time.Now()
	}
}

func (r *WorkerRegistry) Completed(id string, status int) {
	r.mu.Lock()
	defer r.mu.Unlock()
	entry, ok := r.workers[id]
	if !ok {
		return
	}
	entry.completed++
	if status == CRITICAL || status == KILLED {
		entry.failed++
	}
	entry.lastSeen = time.Now()
}

func (r *WorkerRegistry) Touch(id string) bool {
	r.mu.Lock()
	defer r.mu.Unlock()
	entry, ok := r.workers[id]
	if !ok {
		return false
	}
	entry.lastSeen = time.Now()
	return true
}

func (r *WorkerRegistry) Remove(id string) {
	r.mu.Lock()
	defer r.mu.Unlock()
	delete(r.workers, id)
}

func (r *WorkerRegistry) List() []WorkerView {
	r.mu.RLock()
	defer r.mu.RUnlock()
	out := make([]WorkerView, 0, len(r.workers))
	for _, entry := range r.workers {
		out = append(out, WorkerView{
			WorkerRegistration: entry.reg,
			Running:            entry.running,
			Completed:          entry.completed,
			Failed:             entry.failed,
			LastSeen:           entry.lastSeen,
			Alive:              time.Since(entry.lastSeen) < workerStaleAfter,
		})
	}
	sort.Slice(out, func(i, j int) bool { return out[i].Name < out[j].Name })
	return out
}

// NameOf resolves a worker id to the node name a human recognises. Falls back
// to the id, which is all there is left once a worker is gone.
func (r *WorkerRegistry) NameOf(id string) string {
	r.mu.RLock()
	defer r.mu.RUnlock()
	if entry, ok := r.workers[id]; ok && entry.reg.Name != "" {
		return entry.reg.Name
	}
	return id
}

// LiveNames are the names of the workers currently checking in.
func (r *WorkerRegistry) LiveNames() map[string]bool {
	r.mu.RLock()
	defer r.mu.RUnlock()
	out := make(map[string]bool, len(r.workers))
	for _, entry := range r.workers {
		if time.Since(entry.lastSeen) < workerStaleAfter {
			out[entry.reg.Name] = true
		}
	}
	return out
}

// Capacity is the total number of checks the cluster can run in parallel.
func (r *WorkerRegistry) Capacity() int {
	r.mu.RLock()
	defer r.mu.RUnlock()
	total := 0
	for _, entry := range r.workers {
		if time.Since(entry.lastSeen) < workerStaleAfter {
			total += entry.reg.Capacity
		}
	}
	return total
}

func (r *WorkerRegistry) persist() {
	views := r.List()
	conn := db.ConnectDB()
	ctx := context.Background()
	for _, v := range views {
		row := &db.WorkerNode{
			ID:        v.ID,
			Name:      v.Name,
			Address:   v.Address,
			Capacity:  v.Capacity,
			Embedded:  v.Embedded,
			Enabled:   true,
			Running:   v.Running,
			Completed: v.Completed,
			Failed:    v.Failed,
			Version:   v.Version,
			FirstSeen: time.Now(),
			LastSeen:  v.LastSeen,
		}
		if _, err := conn.NewInsert().Model(row).
			On("CONFLICT (id) DO UPDATE").
			Set("name = EXCLUDED.name, address = EXCLUDED.address, capacity = EXCLUDED.capacity, running = EXCLUDED.running, completed = EXCLUDED.completed, failed = EXCLUDED.failed, last_seen = EXCLUDED.last_seen").
			Exec(ctx); err != nil {
			log.Debugf("Error persisting worker %v: %v", v.ID, err)
		}
		// A worker that restarted left a row behind under its old id. Same
		// node, same name: drop the ghost rather than let the table grow one
		// entry per restart.
		if _, err := conn.NewDelete().Model((*db.WorkerNode)(nil)).
			Where("name = ? and id <> ?", v.Name, v.ID).Exec(ctx); err != nil {
			log.Debugf("Error pruning stale workers named %v: %v", v.Name, err)
		}
	}
}

// ----------------------------------------------------------------------------
// cluster HTTP API (internal, never exposed to players)
// ----------------------------------------------------------------------------

func validClusterToken(token string) bool {
	return subtle.ConstantTimeCompare([]byte(token), []byte(conf.Token)) == 1
}

func handleWorkerHello(w http.ResponseWriter, r *http.Request) {
	var req workerHelloRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil || !validClusterToken(req.Token) {
		http.Error(w, "Unauthorized", http.StatusUnauthorized)
		return
	}
	if req.Capacity <= 0 {
		req.Capacity = 1
	}
	reg := &WorkerRegistration{
		Name:     req.Name,
		Address:  clientIP(r),
		Capacity: req.Capacity,
		Version:  req.Version,
	}
	id := registry.Register(reg)
	log.Infof("Checker worker %v (%v) joined with %d slots", reg.Name, id, reg.Capacity)
	auditLog("cluster", "worker.join", reg.Name, "capacity="+itoa(reg.Capacity))

	writeJSON(w, workerHelloResponse{WorkerID: id, Round: db.GetExposedRound()})
}

func handleWorkerClaim(w http.ResponseWriter, r *http.Request) {
	var req workerClaimRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil || !validClusterToken(req.Token) {
		http.Error(w, "Unauthorized", http.StatusUnauthorized)
		return
	}
	if !registry.Touch(req.WorkerID) {
		// The control node restarted: ask the worker to say hello again.
		http.Error(w, "Unknown worker", http.StatusGone)
		return
	}
	max := req.Max
	if max <= 0 {
		max = 1
	}
	if max > 64 {
		max = 64
	}
	jobs := dispatcher.Claim(req.WorkerID, max, 15*time.Second)
	writeJSON(w, jobs)
}

func handleWorkerResult(w http.ResponseWriter, r *http.Request) {
	var req workerResultRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil || !validClusterToken(req.Token) {
		http.Error(w, "Unauthorized", http.StatusUnauthorized)
		return
	}
	registry.Touch(req.WorkerID)
	registry.SetRunning(req.WorkerID, req.Running)
	// Jobs record the node name: the internal id means nothing to the
	// organizer reading the checker log.
	workerName := registry.NameOf(req.WorkerID)
	for _, res := range req.Results {
		res.Worker = workerName
		dispatcher.Complete(res)
		registry.Completed(req.WorkerID, res.Status)
	}
	w.WriteHeader(http.StatusOK)
}

func clientIP(r *http.Request) string {
	if forwarded := r.Header.Get("X-Forwarded-For"); forwarded != "" {
		return forwarded
	}
	return r.RemoteAddr
}

func writeJSON(w http.ResponseWriter, payload interface{}) {
	w.Header().Set("Content-Type", "application/json")
	if err := json.NewEncoder(w).Encode(payload); err != nil {
		log.Errorf("Error encoding response: %v", err)
	}
}

func serveClusterAPI() {
	router := mux.NewRouter()

	router.HandleFunc("/worker/hello", handleWorkerHello).Methods("POST")
	router.HandleFunc("/worker/claim", handleWorkerClaim).Methods("POST")
	router.HandleFunc("/worker/result", handleWorkerResult).Methods("POST")
	router.HandleFunc("/node/traffic", handleTrafficIngest).Methods("POST")
	router.HandleFunc("/cluster/node-sync", handleNodeSync).Methods("POST")
	router.HandleFunc("/cluster/health", func(w http.ResponseWriter, r *http.Request) {
		writeJSON(w, map[string]interface{}{
			"role":     processRole,
			"node":     processNode,
			"round":    db.GetExposedRound(),
			"workers":  len(registry.List()),
			"nodes":    len(nodeRegistry.Statuses()),
			"capacity": registry.Capacity(),
			"queue":    dispatcher.Stats(),
		})
	}).Methods("GET")

	go func() {
		ticker := time.NewTicker(10 * time.Second)
		defer ticker.Stop()
		for range ticker.C {
			registry.persist()
		}
	}()

	log.Noticef("Starting cluster API on :8082")
	srv := &http.Server{
		Handler:      compressMiddleware(router),
		Addr:         "0.0.0.0:8082",
		WriteTimeout: 60 * time.Second,
		ReadTimeout:  60 * time.Second,
	}
	log.Fatal(srv.ListenAndServe())
}

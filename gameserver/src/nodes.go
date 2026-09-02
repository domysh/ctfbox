package main

import (
	"encoding/json"
	"net/http"
	"sort"
	"sync"
	"time"

	"game/log"
)

/*
	Every router of the deployment checks in here on its reconcile tick. That one
	call does three jobs at once: it tells the control node the router is alive
	and what its ruleset currently looks like, it hands back the state the router
	must converge to, and it teaches the control node the address to reach that
	router at.

	The address is the source of the request rather than something configured:
	a remote router answers on its mesh address, which nothing outside the game
	network can even route to, and which no configuration file has to repeat.
*/

const nodeStaleAfter = 45 * time.Second

type NodeStatus struct {
	Name         string    `json:"name"`
	Address      string    `json:"address"`
	Roles        []string  `json:"roles"`
	NetworkState string    `json:"network_state"`
	BannedTeams  []int     `json:"banned_teams"`
	Version      string    `json:"version"`
	FirstSeen    time.Time `json:"first_seen"`
	LastSeen     time.Time `json:"last_seen"`
	Alive        bool      `json:"alive"`
	Seen         bool      `json:"seen"`
}

type nodeEntry struct {
	address      string
	networkState string
	banned       []int
	version      string
	firstSeen    time.Time
	lastSeen     time.Time
}

type NodeRegistry struct {
	mu    sync.RWMutex
	nodes map[string]*nodeEntry
}

var nodeRegistry = &NodeRegistry{nodes: make(map[string]*nodeEntry)}

func (r *NodeRegistry) record(name string, address string, state string, banned []int, version string) {
	r.mu.Lock()
	defer r.mu.Unlock()
	entry, ok := r.nodes[name]
	if !ok {
		entry = &nodeEntry{firstSeen: time.Now()}
		r.nodes[name] = entry
		log.Infof("Router node %v joined from %v", name, address)
	}
	entry.address = address
	entry.networkState = state
	entry.banned = banned
	entry.version = version
	entry.lastSeen = time.Now()
}

// Address is where to reach a node's agent, or "" if it never checked in.
func (r *NodeRegistry) Address(name string) string {
	r.mu.RLock()
	defer r.mu.RUnlock()
	if entry, ok := r.nodes[name]; ok {
		return entry.address
	}
	return ""
}

// Statuses merges the declared topology with what actually checked in, so that
// a node which is configured but silent is visible as such instead of missing.
func (r *NodeRegistry) Statuses() []NodeStatus {
	r.mu.RLock()
	defer r.mu.RUnlock()

	declared := conf.Nodes
	if len(declared) == 0 {
		declared = []NodeInfo{{
			Name:  processNode,
			Roles: []string{"control", "vpn", "vm", "checker"},
		}}
	}

	// A node whose only job is running checkers has no router, so it never
	// checks in here: its worker checking in is what proves it is alive.
	liveWorkers := registry.LiveNames()

	out := make([]NodeStatus, 0, len(declared))
	seen := make(map[string]bool, len(declared))
	for _, node := range declared {
		seen[node.Name] = true
		status := NodeStatus{Name: node.Name, Roles: node.Roles, Address: node.Address}
		if entry, ok := r.nodes[node.Name]; ok {
			status.Address = entry.address
			status.NetworkState = entry.networkState
			status.BannedTeams = entry.banned
			status.Version = entry.version
			status.FirstSeen = entry.firstSeen
			status.LastSeen = entry.lastSeen
			status.Alive = time.Since(entry.lastSeen) < nodeStaleAfter
			status.Seen = true
		}
		if liveWorkers[node.Name] {
			status.Alive = true
			status.Seen = true
		}
		out = append(out, status)
	}
	// A router that checked in without being declared is worth showing too.
	for name, entry := range r.nodes {
		if seen[name] {
			continue
		}
		out = append(out, NodeStatus{
			Name:         name,
			Address:      entry.address,
			NetworkState: entry.networkState,
			BannedTeams:  entry.banned,
			Version:      entry.version,
			FirstSeen:    entry.firstSeen,
			LastSeen:     entry.lastSeen,
			Alive:        time.Since(entry.lastSeen) < nodeStaleAfter,
			Seen:         true,
		})
	}
	sort.Slice(out, func(i, j int) bool { return out[i].Name < out[j].Name })
	return out
}

type nodeSyncRequest struct {
	Token  string `json:"token"`
	Node   string `json:"node"`
	State  string `json:"state"`
	Banned []int  `json:"banned"`
	// Suspended are the VPN profiles this router currently has cut off, so the
	// control node can show what is actually in force rather than what it asked
	// for.
	Suspended []string `json:"suspended"`
	Version   string   `json:"version"`
}

type nodeSyncResponse struct {
	State     string   `json:"state"`
	Banned    []int    `json:"banned"`
	Suspended []string `json:"suspended"`
}

// handleNodeSync is the heartbeat and the state exchange of a router agent.
func handleNodeSync(w http.ResponseWriter, r *http.Request) {
	var req nodeSyncRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil || !validClusterToken(req.Token) {
		http.Error(w, "Unauthorized", http.StatusUnauthorized)
		return
	}
	name := req.Node
	if name == "" {
		name = "unnamed"
	}
	address := ""
	if ip := peerIP(r); ip != nil {
		address = ip.String()
	}
	nodeRegistry.record(name, address, req.State, req.Banned, req.Version)

	banned := make([]int, 0)
	for _, team := range gs.Teams() {
		if team.NetworkBanned {
			banned = append(banned, team.ID)
		}
	}
	writeJSON(w, nodeSyncResponse{
		State:     gs.NetworkState(),
		Banned:    banned,
		Suspended: gs.SuspendedProfiles(),
	})
}

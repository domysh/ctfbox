package main

import (
	"encoding/json"
	"fmt"
	"os"
	"strconv"
	"strings"
	"sync"
	"time"
)

const configPath = "../config.json"

// TeamInfo is the bootstrap description of a team as written in config.json.
type TeamInfo struct {
	ID    int     `json:"id"`
	Token *string `json:"token"`
	Name  string  `json:"name"`
	Image string  `json:"image"`
	Nop   bool    `json:"nop"`
	Node  string  `json:"node,omitempty"`
}

// NodeInfo describes one machine of a distributed deployment. A single-machine
// deployment simply has no nodes declared and everything runs locally.
type NodeInfo struct {
	Name               string   `json:"name"`
	Roles              []string `json:"roles"`
	Address            string   `json:"address"`
	PublicAddress      string   `json:"public_address,omitempty"`
	SSH                string   `json:"ssh,omitempty"`
	Path               string   `json:"path,omitempty"`
	Weight             int      `json:"weight,omitempty"`
	CheckerConcurrency int      `json:"checker_concurrency,omitempty"`
	// Teams whose tunnels terminate on this node, and whose vulnbox runs on it.
	// The two are independent: several VM nodes can hang off one VPN node.
	Teams   []int `json:"teams,omitempty"`
	VMTeams []int `json:"vm_teams,omitempty"`
}

func (n *NodeInfo) HasRole(role string) bool {
	for _, r := range n.Roles {
		if r == role {
			return true
		}
	}
	return false
}

// Config is the raw content of config.json. Everything that can legitimately
// change while the game is running is copied into GameState at boot and from
// then on the database is the authority (see state.go).
type Config struct {
	Token               string     `json:"gameserver_token"`
	Teams               []TeamInfo `json:"teams"`
	Round               int64      `json:"tick_time"`
	FlagExpireTicks     int64      `json:"flag_expire_ticks"`
	InitialServiceScore float64    `json:"initial_service_score"`
	SubmitterTimeout    *float64   `json:"submission_timeout"`
	MaxFlagsPerRequest  int        `json:"max_flags_per_request"`
	Debug               bool       `json:"debug"`
	StartTime           *string    `json:"start_time"`
	EndTime             *string    `json:"end_time"`
	GraceTime           *int64     `json:"grace_time"`
	ScoreboardFreeze    *string    `json:"scoreboard_freeze_time"`
	CheckerConcurrency  int        `json:"checker_concurrency"`
	CheckerTimeout      int64      `json:"checker_timeout"`
	// How the team boxes are run: incus, incus-vm, privileged or none. The
	// control room needs it to know whether a box can be reset at all.
	VMMode string     `json:"vm_mode"`
	Nodes  []NodeInfo `json:"nodes"`
}

var conf *Config

// role of this process: "control" runs the whole game server, "worker" only
// executes checkers for a remote control node.
var (
	processRole    = "control"
	processNode    = "main"
	controlBaseURL = ""
)

func loadRawConfig(path string) (*Config, error) {
	c := &Config{}
	file, err := os.Open(path)
	if err != nil {
		return c, err
	}
	defer file.Close()

	if err = json.NewDecoder(file).Decode(c); err != nil {
		return c, err
	}
	return c, nil
}

func extractTeamID(ip string) int {
	teamID := 0
	splitted := strings.Split(ip, ".")
	if len(splitted) == 4 {
		teamID, _ = strconv.Atoi(splitted[2])
	}
	return teamID
}

func teamIDToIP(teamID int) string {
	return fmt.Sprintf("10.60.%d.1", teamID)
}

// configMutationLock serialises the read-modify-write cycles on config.json so
// that two concurrent admin requests cannot lose each other's changes.
var configMutationLock sync.Mutex

// patchConfigFile applies a shallow patch to config.json preserving every key
// the game server does not know about (the file is also read by run.py).
func patchConfigFile(patch map[string]interface{}) error {
	configMutationLock.Lock()
	defer configMutationLock.Unlock()

	raw, err := os.ReadFile(configPath)
	if err != nil {
		return err
	}
	var data map[string]interface{}
	if err := json.Unmarshal(raw, &data); err != nil {
		return err
	}
	for k, v := range patch {
		if v == nil {
			data[k] = nil
			continue
		}
		data[k] = v
	}
	out, err := json.MarshalIndent(data, "", "    ")
	if err != nil {
		return err
	}
	// Written in place on purpose: config.json is a single file bind mount, so
	// the usual write-to-temp-and-rename dance fails with EBUSY/EXDEV.
	return os.WriteFile(configPath, out, 0o644)
}

func parseTimePtr(value *string) (*time.Time, error) {
	if value == nil || strings.TrimSpace(*value) == "" {
		return nil, nil
	}
	parsed, err := time.Parse(time.RFC3339, *value)
	if err != nil {
		return nil, err
	}
	return &parsed, nil
}

package db

import (
	"time"

	"github.com/uptrace/bun"
)

/*
	Historical note: teams and services used to live only in config.json and were
	referenced everywhere by their IP address. They are now mirrored inside the
	database so that the admin panel can mutate them at runtime (rename, ban,
	rotate tokens, disable a service, ...) while config.json stays the bootstrap
	source of truth. The IP address is still the join key of every scoring table
	to keep backwards compatibility with existing databases.
*/

type FlagIdWrapper struct {
	K interface{} `json:"k"`
}

type Flag struct {
	bun.BaseModel  `bun:"table:flags,alias:flag" json:"-"`
	ID             string        `bun:",pk" json:"id"`
	Team           string        `bun:",notnull" json:"team"`
	Round          uint          `bun:",notnull" json:"round"`
	Service        string        `bun:",notnull" json:"service"`
	CreatedAt      time.Time     `bun:",notnull,default:current_timestamp" json:"created_at"`
	ExternalFlagId FlagIdWrapper `bun:"type:jsonb" json:"external_flag_id"`
	// CheckerData is the replacement of the on-disk `flag_ids/` directory the
	// checkers used to write into: with distributed checkers PUT_FLAG and
	// GET_FLAG of the same flag may run on two different machines.
	CheckerData FlagIdWrapper `bun:"type:jsonb" json:"-"`
}

type FlagSubmission struct {
	bun.BaseModel   `bun:"table:flag_submissions,alias:submit"`
	ID              int64     `bun:",pk,autoincrement"`
	FlagID          string    `bun:",notnull,unique:team"`
	Team            string    `bun:",notnull,unique:team"`
	OffensivePoints float64   `bun:",notnull"`
	DefensivePoints float64   `bun:",notnull"`
	SubmittedAt     time.Time `bun:",notnull,default:current_timestamp"`
	Round           uint      `bun:",notnull,default:0"`
	Flag            *Flag     `bun:"rel:belongs-to,join:flag_id=id"`
}

type StatusHistory struct {
	bun.BaseModel  `bun:"table:sla_statues"`
	ID             int64  `bun:",pk,autoincrement"`
	Team           string `bun:",notnull,unique:sla-check"`
	Service        string `bun:",notnull,unique:sla-check"`
	Round          uint   `bun:",notnull,unique:sla-check"`
	PutFlagStatus  int    `bun:",notnull"`
	PutFlagMessage string
	PutFlagAt      time.Time `bun:",notnull"`
	GetFlagStatus  int       `bun:",notnull"`
	GetFlagMessage string
	GetFlagAt      time.Time `bun:",notnull"`
	CheckStatus    int       `bun:",notnull"`
	CheckMessage   string
	CheckdAt       time.Time `bun:",notnull"`
	Sla            float64   `bun:""`
	Score          float64   `bun:""`
	LostFlags      uint      `bun:""`
	DefensePoints  float64   `bun:""`
	StolenFlags    uint      `bun:""`
	OffensePoints  float64   `bun:""`
	SlaUpTimes     uint      `bun:""`
	SlaTotTimes    uint      `bun:""`
}

type ServiceScore struct {
	bun.BaseModel `bun:"table:service_scores"`
	ID            int64   `bun:",pk,autoincrement"`
	Team          string  `bun:",notnull"`
	Service       string  `bun:",notnull"`
	Offense       float64 `bun:",notnull"`
	Defense       float64 `bun:",notnull"`
	Score         float64 `bun:",notnull"`
}

type Environment struct {
	bun.BaseModel `bun:"table:environments"`
	Key           string `bun:",pk"`
	Value         string `bun:",notnull"`
}

// Team mirrors the teams declared in config.json and adds the runtime-only
// fields the organizers can flip during the game.
type Team struct {
	bun.BaseModel `bun:"table:teams,alias:team"`
	ID            int    `bun:",pk"`
	Name          string `bun:",notnull"`
	Token         string `bun:",notnull"`
	Image         string `bun:""`
	Nop           bool   `bun:",notnull,default:false"`
	// GameBanned rejects flag submissions and freezes the team on the scoreboard.
	GameBanned bool `bun:",notnull,default:false"`
	// NetworkBanned drops every packet coming from the team VPN subnet.
	NetworkBanned bool      `bun:",notnull,default:false"`
	BanReason     string    `bun:""`
	Node          string    `bun:""`
	UpdatedAt     time.Time `bun:",notnull,default:current_timestamp"`
}

// Service mirrors the checkers directory, adding an enable switch and the
// per-service scoring weight.
type Service struct {
	bun.BaseModel `bun:"table:services,alias:service"`
	Name          string    `bun:",pk"`
	Enabled       bool      `bun:",notnull,default:true"`
	Weight        float64   `bun:",notnull,default:1"`
	Description   string    `bun:""`
	UpdatedAt     time.Time `bun:",notnull,default:current_timestamp"`
}

// Setting is the runtime-mutable game configuration. config.json seeds it on
// the very first boot, afterwards the database wins so that a restart never
// silently reverts what the organizers changed mid-game.
type Setting struct {
	bun.BaseModel `bun:"table:settings"`
	Key           string    `bun:",pk"`
	Value         string    `bun:",notnull"`
	UpdatedAt     time.Time `bun:",notnull,default:current_timestamp"`
}

// CheckJob is one unit of work handed to a checker worker. Persisting it makes
// the admin panel able to show what every worker is doing and lets the
// scheduler recover jobs lost with a crashed worker.
type CheckJob struct {
	bun.BaseModel `bun:"table:check_jobs,alias:job" json:"-"`
	ID            int64      `bun:",pk,autoincrement" json:"id"`
	Round         uint       `bun:",notnull" json:"round"`
	TeamID        int        `bun:",notnull" json:"team_id"`
	Team          string     `bun:",notnull" json:"team"`
	Service       string     `bun:",notnull" json:"service"`
	Action        string     `bun:",notnull" json:"action"`
	Flag          string     `bun:"" json:"flag"`
	State         string     `bun:",notnull" json:"state"` // queued|running|done|lost
	Worker        string     `bun:"" json:"worker"`
	Status        int        `bun:",notnull,default:0" json:"status"`
	Message       string     `bun:"" json:"message"`
	CreatedAt     time.Time  `bun:",notnull,default:current_timestamp" json:"created_at"`
	StartedAt     *time.Time `json:"started_at"`
	FinishedAt    *time.Time `json:"finished_at"`
	DurationMs    int64      `bun:",notnull,default:0" json:"duration_ms"`
}

// WorkerNode is a checker runner (either the embedded one or a remote node).
type WorkerNode struct {
	bun.BaseModel `bun:"table:worker_nodes,alias:worker"`
	ID            string    `bun:",pk"`
	Name          string    `bun:",notnull"`
	Address       string    `bun:""`
	Capacity      int       `bun:",notnull,default:1"`
	Embedded      bool      `bun:",notnull,default:false"`
	Enabled       bool      `bun:",notnull,default:true"`
	Running       int       `bun:",notnull,default:0"`
	Completed     int64     `bun:",notnull,default:0"`
	Failed        int64     `bun:",notnull,default:0"`
	Version       string    `bun:""`
	FirstSeen     time.Time `bun:",notnull,default:current_timestamp"`
	LastSeen      time.Time `bun:",notnull,default:current_timestamp"`
}

// TrafficSample is one accounting window pushed by a router node.
type TrafficSample struct {
	bun.BaseModel `bun:"table:traffic_samples,alias:traffic"`
	ID            int64     `bun:",pk,autoincrement"`
	At            time.Time `bun:",notnull,default:current_timestamp"`
	Round         int       `bun:",notnull,default:-1"`
	Node          string    `bun:",notnull"`
	// Kind is "vm" (traffic towards a team vulnbox) or "vpn" (player tunnel).
	Kind    string `bun:",notnull"`
	SrcTeam int    `bun:",notnull"`
	DstTeam int    `bun:",notnull"`
	Bytes   int64  `bun:",notnull"`
	Packets int64  `bun:",notnull"`
	// Conns counts the flows opened in the window (conntrack NEW), which is a
	// far better attack signal than the raw packet count.
	Conns int64 `bun:",notnull,default:0"`
}

// PeerSample is the traffic of one VPN profile over a collection window, taken
// from WireGuard's own per peer counters. One row per profile per window, which
// is what answers "who inside that team is consuming all of this".
type PeerSample struct {
	bun.BaseModel `bun:"table:peer_samples,alias:peer"`
	ID            int64     `bun:",pk,autoincrement"`
	At            time.Time `bun:",notnull,default:current_timestamp"`
	Round         int       `bun:",notnull,default:-1"`
	Node          string    `bun:",notnull"`
	// TeamID is -1 for the organizers' own profiles.
	TeamID  int    `bun:",notnull"`
	Profile int    `bun:",notnull"`
	Address string `bun:",notnull"`
	Rx      int64  `bun:",notnull"`
	Tx      int64  `bun:",notnull"`
	// Handshake is the unix time of the peer's last handshake, 0 if it never
	// connected: it is what tells a quiet profile from an unused one.
	Handshake int64 `bun:",notnull,default:0"`
}

// SubmissionEvent records one flag submission attempt, accepted or not. The
// accepted ones also land in flag_submissions (that table is what scores the
// game); this one exists to answer "what are the teams actually submitting".
type SubmissionEvent struct {
	bun.BaseModel `bun:"table:submission_events,alias:subev" json:"-"`
	ID            int64     `bun:",pk,autoincrement" json:"id"`
	At            time.Time `bun:",notnull,default:current_timestamp" json:"at"`
	Round         int       `bun:",notnull,default:-1" json:"round"`
	TeamID        int       `bun:",notnull,default:-1" json:"team_id"`
	Team          string    `bun:",notnull" json:"team"`
	// VictimID/Victim and Service are only known once the flag was recognised.
	VictimID int    `bun:",notnull,default:-1" json:"victim_id"`
	Victim   string `bun:"" json:"victim"`
	Service  string `bun:"" json:"service"`
	Flag     string `bun:"" json:"flag"`
	Status   string `bun:",notnull" json:"status"`
	// Reason is the machine readable version of the message: accepted, own,
	// expired, duplicate, invalid, nop, banned, error.
	Reason string  `bun:",notnull" json:"reason"`
	Points float64 `bun:",notnull,default:0" json:"points"`
}

// AuditLog records every privileged action performed through the admin panel.
type AuditLog struct {
	bun.BaseModel `bun:"table:audit_logs,alias:audit" json:"-"`
	ID            int64     `bun:",pk,autoincrement" json:"id"`
	At            time.Time `bun:",notnull,default:current_timestamp" json:"at"`
	Actor         string    `bun:",notnull" json:"actor"`
	Action        string    `bun:",notnull" json:"action"`
	Target        string    `bun:"" json:"target"`
	Details       string    `bun:"" json:"details"`
}

// Announcement is a message broadcast to every player on the scoreboard.
type Announcement struct {
	bun.BaseModel `bun:"table:announcements,alias:ann" json:"-"`
	ID            int64     `bun:",pk,autoincrement" json:"id"`
	At            time.Time `bun:",notnull,default:current_timestamp" json:"at"`
	Title         string    `bun:",notnull" json:"title"`
	Body          string    `bun:"" json:"body"`
	Severity      string    `bun:",notnull,default:'info'" json:"severity"` // info|warning|critical
	Visible       bool      `bun:",notnull,default:true" json:"visible"`
	Author        string    `bun:"" json:"author"`
}

/*

DB ENVIRONMENT VARIABLES

START_TIME            - The time the game started
ACTUAL_ROUND_EXPOSED  - The current round exposed in the APIs

Runtime settings live in the `settings` table instead, see settings.go.

*/

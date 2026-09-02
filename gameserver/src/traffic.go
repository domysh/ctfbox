package main

import (
	"context"
	"encoding/json"
	"net/http"
	"strconv"
	"time"

	"game/db"
	"game/log"
)

// TrafficReport is what a router agent pushes every collection window.
type TrafficReport struct {
	Token   string          `json:"token"`
	Node    string          `json:"node"`
	Samples []TrafficSample `json:"samples"`
	// Peers are the per VPN profile counters WireGuard keeps on its own.
	Peers []PeerTraffic `json:"peers"`
}

// PeerTraffic is one VPN profile's share of the traffic in a window.
type PeerTraffic struct {
	Team      int    `json:"team"`
	Profile   int    `json:"profile"`
	Address   string `json:"address"`
	Rx        int64  `json:"rx"`
	Tx        int64  `json:"tx"`
	Handshake int64  `json:"handshake"`
}

type TrafficSample struct {
	Kind    string `json:"kind"` // "vm" (towards a vulnbox) or "vpn" (player tunnel)
	SrcTeam int    `json:"src_team"`
	DstTeam int    `json:"dst_team"`
	Bytes   int64  `json:"bytes"`
	Packets int64  `json:"packets"`
	Conns   int64  `json:"conns"`
}

func handleTrafficIngest(w http.ResponseWriter, r *http.Request) {
	var report TrafficReport
	if err := json.NewDecoder(r.Body).Decode(&report); err != nil || !validClusterToken(report.Token) {
		http.Error(w, "Unauthorized", http.StatusUnauthorized)
		return
	}
	if len(report.Samples) == 0 && len(report.Peers) == 0 {
		w.WriteHeader(http.StatusOK)
		return
	}
	node := report.Node
	if node == "" {
		node = "unknown"
	}
	round := db.GetExposedRound()
	now := time.Now()

	rows := make([]db.TrafficSample, 0, len(report.Samples))
	for _, sample := range report.Samples {
		if sample.Bytes == 0 && sample.Packets == 0 && sample.Conns == 0 {
			continue
		}
		rows = append(rows, db.TrafficSample{
			At:      now,
			Round:   round,
			Node:    node,
			Kind:    sample.Kind,
			SrcTeam: sample.SrcTeam,
			DstTeam: sample.DstTeam,
			Bytes:   sample.Bytes,
			Packets: sample.Packets,
			Conns:   sample.Conns,
		})
	}
	peerRows := make([]db.PeerSample, 0, len(report.Peers))
	for _, peer := range report.Peers {
		if peer.Rx == 0 && peer.Tx == 0 {
			continue
		}
		peerRows = append(peerRows, db.PeerSample{
			At:        now,
			Round:     round,
			Node:      node,
			TeamID:    peer.Team,
			Profile:   peer.Profile,
			Address:   peer.Address,
			Rx:        peer.Rx,
			Tx:        peer.Tx,
			Handshake: peer.Handshake,
		})
	}

	if len(rows) > 0 {
		if _, err := conn.NewInsert().Model(&rows).Exec(r.Context()); err != nil {
			log.Errorf("Error storing traffic samples: %v", err)
			http.Error(w, "Internal server error", http.StatusInternalServerError)
			return
		}
	}
	if len(peerRows) > 0 {
		if _, err := conn.NewInsert().Model(&peerRows).Exec(r.Context()); err != nil {
			log.Errorf("Error storing peer samples: %v", err)
			http.Error(w, "Internal server error", http.StatusInternalServerError)
			return
		}
	}
	w.WriteHeader(http.StatusOK)
}

func queryMinutes(r *http.Request, fallback int) int {
	minutes := fallback
	if raw := r.URL.Query().Get("minutes"); raw != "" {
		if parsed, err := strconv.Atoi(raw); err == nil && parsed > 0 && parsed <= 24*60 {
			minutes = parsed
		}
	}
	return minutes
}

type trafficPoint struct {
	At      time.Time `json:"at" bun:"bucket"`
	Team    int       `json:"team" bun:"team"`
	Kind    string    `json:"kind" bun:"kind"`
	Bytes   int64     `json:"bytes" bun:"bytes"`
	Packets int64     `json:"packets" bun:"packets"`
	Conns   int64     `json:"conns" bun:"conns"`
}

// handleAdminTraffic returns a per-team time series, bucketed so that the chart
// stays readable whatever window the organizers pick.
func handleAdminTraffic(w http.ResponseWriter, r *http.Request) {
	minutes := queryMinutes(r, 60)
	bucketSeconds := minutes * 60 / 120 // ~120 points per chart
	if bucketSeconds < 10 {
		bucketSeconds = 10
	}
	since := time.Now().Add(-time.Duration(minutes) * time.Minute)

	rows := make([]trafficPoint, 0)
	query := conn.NewSelect().Model((*db.TrafficSample)(nil)).
		ColumnExpr("to_timestamp(floor(extract(epoch from at) / ?) * ?) AS bucket", bucketSeconds, bucketSeconds).
		ColumnExpr("src_team AS team").
		ColumnExpr("kind").
		ColumnExpr("sum(bytes) AS bytes").
		ColumnExpr("sum(packets) AS packets").
		ColumnExpr("sum(conns) AS conns").
		Where("at >= ?", since).
		GroupExpr("bucket, src_team, kind").
		OrderExpr("bucket ASC")

	if team := r.URL.Query().Get("team"); team != "" {
		query = query.Where("src_team = ?", team)
	}
	if kind := r.URL.Query().Get("kind"); kind != "" {
		query = query.Where("kind = ?", kind)
	}
	if err := query.Scan(r.Context(), &rows); err != nil {
		log.Errorf("Error querying traffic: %v", err)
		http.Error(w, "Internal server error", http.StatusInternalServerError)
		return
	}
	writeJSON(w, map[string]interface{}{
		"minutes":        minutes,
		"bucket_seconds": bucketSeconds,
		"points":         rows,
	})
}

type trafficMatrixEntry struct {
	SrcTeam int    `json:"src_team" bun:"src_team"`
	DstTeam int    `json:"dst_team" bun:"dst_team"`
	Bytes   int64  `json:"bytes" bun:"bytes"`
	Packets int64  `json:"packets" bun:"packets"`
	Conns   int64  `json:"conns" bun:"conns"`
	Kind    string `json:"kind" bun:"kind"`
}

// handleAdminTrafficMatrix answers "who is hitting whom" from the network point
// of view, which complements the attack graph built from the submissions.
func handleAdminTrafficMatrix(w http.ResponseWriter, r *http.Request) {
	minutes := queryMinutes(r, 15)
	since := time.Now().Add(-time.Duration(minutes) * time.Minute)

	rows := make([]trafficMatrixEntry, 0)
	if err := conn.NewSelect().Model((*db.TrafficSample)(nil)).
		ColumnExpr("src_team").
		ColumnExpr("dst_team").
		ColumnExpr("kind").
		ColumnExpr("sum(bytes) AS bytes").
		ColumnExpr("sum(packets) AS packets").
		ColumnExpr("sum(conns) AS conns").
		Where("at >= ?", since).
		GroupExpr("src_team, dst_team, kind").
		OrderExpr("bytes DESC").
		Limit(2000).
		Scan(r.Context(), &rows); err != nil {
		log.Errorf("Error querying traffic matrix: %v", err)
		http.Error(w, "Internal server error", http.StatusInternalServerError)
		return
	}
	writeJSON(w, map[string]interface{}{"minutes": minutes, "edges": rows})
}

// handleAdminPeerTraffic answers "who inside a team is consuming what": one row
// per VPN profile over the window, with the team totals built from them.
func handleAdminPeerTraffic(w http.ResponseWriter, r *http.Request) {
	minutes := queryMinutes(r, 60)
	since := time.Now().Add(-time.Duration(minutes) * time.Minute)

	type peerRow struct {
		TeamID    int    `json:"team_id" bun:"team_id"`
		Profile   int    `json:"profile" bun:"profile"`
		Address   string `json:"address" bun:"address"`
		Node      string `json:"node" bun:"node"`
		Rx        int64  `json:"rx" bun:"rx"`
		Tx        int64  `json:"tx" bun:"tx"`
		Handshake int64  `json:"handshake" bun:"handshake"`
	}

	rows := make([]peerRow, 0)
	query := conn.NewSelect().Model((*db.PeerSample)(nil)).
		ColumnExpr("team_id").
		ColumnExpr("profile").
		ColumnExpr("address").
		ColumnExpr("max(node) AS node").
		ColumnExpr("sum(rx) AS rx").
		ColumnExpr("sum(tx) AS tx").
		ColumnExpr("max(handshake) AS handshake").
		Where("at >= ?", since).
		GroupExpr("team_id, profile, address").
		OrderExpr("team_id ASC, profile ASC")
	if team := r.URL.Query().Get("team"); team != "" {
		query = query.Where("team_id = ?", team)
	}
	if err := query.Scan(r.Context(), &rows); err != nil {
		log.Errorf("Error querying peer traffic: %v", err)
		http.Error(w, "Internal server error", http.StatusInternalServerError)
		return
	}

	type teamRow struct {
		TeamID   int   `json:"team_id"`
		Rx       int64 `json:"rx"`
		Tx       int64 `json:"tx"`
		Profiles int   `json:"profiles"`
		Active   int   `json:"active"`
	}
	totals := make(map[int]*teamRow)
	order := make([]int, 0)
	recent := time.Now().Add(-3 * time.Minute).Unix()
	suspended := gs.SuspendedProfiles()
	for _, row := range rows {
		entry, ok := totals[row.TeamID]
		if !ok {
			entry = &teamRow{TeamID: row.TeamID}
			totals[row.TeamID] = entry
			order = append(order, row.TeamID)
		}
		entry.Rx += row.Rx
		entry.Tx += row.Tx
		entry.Profiles++
		if row.Handshake > recent {
			entry.Active++
		}
	}
	teams := make([]teamRow, 0, len(order))
	for _, id := range order {
		teams = append(teams, *totals[id])
	}

	writeJSON(w, map[string]interface{}{
		"minutes":   minutes,
		"profiles":  rows,
		"teams":     teams,
		"suspended": suspended,
	})
}

// pruneTraffic keeps the traffic table bounded; a long competition on a busy
// network would otherwise write millions of rows.
func startTrafficPruner(retention time.Duration) {
	go func() {
		ticker := time.NewTicker(30 * time.Minute)
		defer ticker.Stop()
		for range ticker.C {
			cutoff := time.Now().Add(-retention)
			if _, err := conn.NewDelete().Model((*db.TrafficSample)(nil)).
				Where("at < ?", cutoff).
				Exec(context.Background()); err != nil {
				log.Debugf("Error pruning traffic samples: %v", err)
			}
			if _, err := conn.NewDelete().Model((*db.PeerSample)(nil)).
				Where("at < ?", cutoff).
				Exec(context.Background()); err != nil {
				log.Debugf("Error pruning peer samples: %v", err)
			}
		}
	}()
}

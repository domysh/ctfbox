package main

import (
	"net/http"
	"strconv"
	"time"

	"game/db"
	"game/log"

	"github.com/uptrace/bun"
)

// The admin view of the submission log: the raw attempts and the aggregates
// built on top of them. Every filter is optional and they all compose, so the
// same endpoint answers "everything that happened" and "why is team 4 being
// refused on Notes since round 30".

func submissionFilters(query *bun.SelectQuery, r *http.Request) *bun.SelectQuery {
	q := r.URL.Query()
	if team := q.Get("team"); team != "" {
		query = query.Where("team_id = ?", team)
	}
	if victim := q.Get("victim"); victim != "" {
		query = query.Where("victim_id = ?", victim)
	}
	if service := q.Get("service"); service != "" {
		query = query.Where("service = ?", service)
	}
	if status := q.Get("status"); status != "" {
		query = query.Where("status = ?", status)
	}
	if reason := q.Get("reason"); reason != "" {
		query = query.Where("reason = ?", reason)
	}
	if from := q.Get("from_round"); from != "" {
		query = query.Where("round >= ?", from)
	}
	if to := q.Get("to_round"); to != "" {
		query = query.Where("round <= ?", to)
	}
	if minutes := q.Get("minutes"); minutes != "" {
		if parsed, err := strconv.Atoi(minutes); err == nil && parsed > 0 {
			query = query.Where("at >= ?", time.Now().Add(-time.Duration(parsed)*time.Minute))
		}
	}
	return query
}

func handleAdminSubmissions(w http.ResponseWriter, r *http.Request) {
	limit := 300
	if raw := r.URL.Query().Get("limit"); raw != "" {
		if parsed, err := strconv.Atoi(raw); err == nil && parsed > 0 && parsed <= 2000 {
			limit = parsed
		}
	}
	rows := make([]db.SubmissionEvent, 0)
	query := submissionFilters(conn.NewSelect().Model(&rows), r).
		Order("id DESC").Limit(limit)
	if err := query.Scan(r.Context()); err != nil {
		log.Errorf("Error querying submissions: %v", err)
		http.Error(w, "Internal server error", http.StatusInternalServerError)
		return
	}

	total, err := submissionFilters(conn.NewSelect().Model((*db.SubmissionEvent)(nil)), r).
		Count(r.Context())
	if err != nil {
		log.Errorf("Error counting submissions: %v", err)
		total = len(rows)
	}
	writeJSON(w, map[string]interface{}{
		"total":  total,
		"limit":  limit,
		"events": rows,
	})
}

type submissionReasonStat struct {
	Reason string `json:"reason" bun:"reason"`
	Count  int    `json:"count" bun:"count"`
}

type submissionTeamStat struct {
	TeamID   int     `json:"team_id" bun:"team_id"`
	Total    int     `json:"total" bun:"total"`
	Accepted int     `json:"accepted" bun:"accepted"`
	Points   float64 `json:"points" bun:"points"`
}

type submissionRoundStat struct {
	Round    int `json:"round" bun:"round"`
	Total    int `json:"total" bun:"total"`
	Accepted int `json:"accepted" bun:"accepted"`
}

// handleAdminSubmissionStats answers the three questions worth a dashboard:
// what are the refusals made of, who is submitting, and how it moves per round.
func handleAdminSubmissionStats(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()

	reasons := make([]submissionReasonStat, 0)
	if err := submissionFilters(conn.NewSelect().Model((*db.SubmissionEvent)(nil)), r).
		ColumnExpr("reason").
		ColumnExpr("count(*) AS count").
		GroupExpr("reason").
		OrderExpr("count DESC").
		Scan(ctx, &reasons); err != nil {
		log.Errorf("Error querying submission reasons: %v", err)
		http.Error(w, "Internal server error", http.StatusInternalServerError)
		return
	}

	teams := make([]submissionTeamStat, 0)
	if err := submissionFilters(conn.NewSelect().Model((*db.SubmissionEvent)(nil)), r).
		ColumnExpr("team_id").
		ColumnExpr("count(*) AS total").
		ColumnExpr("count(*) FILTER (WHERE reason = ?) AS accepted", reasonAccepted).
		ColumnExpr("coalesce(sum(points), 0) AS points").
		GroupExpr("team_id").
		OrderExpr("total DESC").
		Scan(ctx, &teams); err != nil {
		log.Errorf("Error querying submission teams: %v", err)
		http.Error(w, "Internal server error", http.StatusInternalServerError)
		return
	}

	rounds := make([]submissionRoundStat, 0)
	if err := submissionFilters(conn.NewSelect().Model((*db.SubmissionEvent)(nil)), r).
		ColumnExpr("round").
		ColumnExpr("count(*) AS total").
		ColumnExpr("count(*) FILTER (WHERE reason = ?) AS accepted", reasonAccepted).
		GroupExpr("round").
		OrderExpr("round ASC").
		Limit(500).
		Scan(ctx, &rounds); err != nil {
		log.Errorf("Error querying submission rounds: %v", err)
		http.Error(w, "Internal server error", http.StatusInternalServerError)
		return
	}

	writeJSON(w, map[string]interface{}{
		"reasons": reasons,
		"teams":   teams,
		"rounds":  rounds,
	})
}

package db

import (
	"context"
	"database/sql"
	"log"
	"os"
	"strconv"
	"sync"
	"time"

	"github.com/uptrace/bun"
	"github.com/uptrace/bun/dialect/pgdialect"
	"github.com/uptrace/bun/driver/pgdriver"
)

const defaultDSN = "postgres://user:pass@database:5432/db?sslmode=disable"

var (
	sharedDB   *bun.DB
	sharedOnce sync.Once
)

func dsn() string {
	if env := os.Getenv("DATABASE_URL"); env != "" {
		return env
	}
	return defaultDSN
}

// ConnectDB returns the process-wide database handle. It used to open a brand
// new pool on every call (including once per HTTP request), which does not
// survive a real competition load.
func ConnectDB() *bun.DB {
	sharedOnce.Do(func() {
		sqldb := sql.OpenDB(pgdriver.NewConnector(pgdriver.WithDSN(dsn())))
		if sqldb == nil {
			panic("failed to connect to database")
		}
		sqldb.SetMaxOpenConns(64)
		sqldb.SetMaxIdleConns(16)
		sqldb.SetConnMaxLifetime(30 * time.Minute)
		sharedDB = bun.NewDB(sqldb, pgdialect.New())
	})
	return sharedDB
}

func GetEnv(key string) *string {
	db := ConnectDB()
	ctx := context.Background()

	envVar := new(Environment)
	if err := db.NewSelect().Model(envVar).Where("key = ?", key).Scan(ctx); err != nil {
		if err == sql.ErrNoRows {
			return nil
		}
		log.Panicf("Error fetching env %v: %v", key, err)
	}
	return &envVar.Value
}

func SetEnv(key string, value string) {
	db := ConnectDB()
	ctx := context.Background()

	if _, err := db.NewInsert().Model(&Environment{Key: key, Value: value}).
		On("CONFLICT (key) DO UPDATE").
		Set("value = EXCLUDED.value").
		Exec(ctx); err != nil {
		log.Panicf("Error storing env %v: %v", key, err)
	}
}

func GetStartTime() *time.Time {
	raw := GetEnv("START_TIME")
	if raw == nil {
		return nil
	}
	startTime, err := time.Parse(time.RFC3339, *raw)
	if err != nil {
		log.Panicf("Error parsing start time: %v", err)
	}
	return &startTime
}

func SetStartTime(startTime time.Time) {
	SetEnv("START_TIME", startTime.Format(time.RFC3339))
}

func GetExposedRound() int {
	raw := GetEnv("ACTUAL_ROUND_EXPOSED")
	if raw == nil {
		SetEnv("ACTUAL_ROUND_EXPOSED", "-1")
		return -1
	}
	exposedRound, err := strconv.Atoi(*raw)
	if err != nil {
		log.Panicf("Error parsing exposed round: %v", err)
	}
	return exposedRound
}

func SetExposedRound(round int64) {
	SetEnv("ACTUAL_ROUND_EXPOSED", strconv.FormatInt(round, 10))
}

func InitDB() {
	var db *bun.DB
	for {
		db = ConnectDB()
		if err := db.Ping(); err == nil {
			break
		}
		log.Printf("Waiting for database to be ready...")
		time.Sleep(1 * time.Second)
	}

	ctx := context.Background()

	models := []interface{}{
		(*Flag)(nil),
		(*FlagSubmission)(nil),
		(*StatusHistory)(nil),
		(*Environment)(nil),
		(*ServiceScore)(nil),
		(*Team)(nil),
		(*Service)(nil),
		(*Setting)(nil),
		(*CheckJob)(nil),
		(*WorkerNode)(nil),
		(*TrafficSample)(nil),
		(*SubmissionEvent)(nil),
		(*PeerSample)(nil),
		(*AuditLog)(nil),
		(*Announcement)(nil),
	}

	// Create tables
	for _, model := range models {
		if _, err := db.NewCreateTable().Model(model).IfNotExists().Exec(ctx); err != nil {
			log.Fatalf("Error creating table model: %v", err)
		}
	}

	// Columns added after the first public release: CreateTable IfNotExists is a
	// no-op on an existing table, so upgrade them explicitly.
	migrations := []string{
		`ALTER TABLE flags ADD COLUMN IF NOT EXISTS checker_data jsonb`,
		`ALTER TABLE flag_submissions ADD COLUMN IF NOT EXISTS round bigint NOT NULL DEFAULT 0`,
		`ALTER TABLE traffic_samples ADD COLUMN IF NOT EXISTS conns bigint NOT NULL DEFAULT 0`,
	}
	for _, stmt := range migrations {
		if _, err := db.ExecContext(ctx, stmt); err != nil {
			log.Fatalf("Error migrating schema (%v): %v", stmt, err)
		}
	}

	GetExposedRound() // Ensure the exposed round is set

	_, err := db.ExecContext(ctx, `
		CREATE INDEX IF NOT EXISTS idx_flags_team ON flags(team);
		CREATE INDEX IF NOT EXISTS idx_flags_round ON flags(round);
		CREATE INDEX IF NOT EXISTS idx_flags_service ON flags(service);
		CREATE INDEX IF NOT EXISTS idx_flags_created_at ON flags(created_at);
		CREATE INDEX IF NOT EXISTS idx_flag_submissions_flag_id ON flag_submissions(flag_id);
		CREATE INDEX IF NOT EXISTS idx_flag_submissions_team ON flag_submissions(team);
		CREATE INDEX IF NOT EXISTS idx_flag_submissions_submitted_at ON flag_submissions(submitted_at);
		CREATE INDEX IF NOT EXISTS idx_flag_submissions_round ON flag_submissions(round);
		CREATE INDEX IF NOT EXISTS idx_sla_statues_team ON sla_statues(team);
		CREATE INDEX IF NOT EXISTS idx_sla_statues_service ON sla_statues(service);
		CREATE INDEX IF NOT EXISTS idx_sla_statues_round ON sla_statues(round);
		CREATE INDEX IF NOT EXISTS idx_service_scores_team ON service_scores(team);
		CREATE INDEX IF NOT EXISTS idx_service_scores_service ON service_scores(service);
		CREATE INDEX IF NOT EXISTS idx_check_jobs_round ON check_jobs(round);
		CREATE INDEX IF NOT EXISTS idx_check_jobs_state ON check_jobs(state);
		CREATE INDEX IF NOT EXISTS idx_traffic_samples_at ON traffic_samples(at);
		CREATE INDEX IF NOT EXISTS idx_traffic_samples_round ON traffic_samples(round);
		CREATE INDEX IF NOT EXISTS idx_traffic_samples_src ON traffic_samples(src_team);
		CREATE INDEX IF NOT EXISTS idx_audit_logs_at ON audit_logs(at);
		CREATE INDEX IF NOT EXISTS idx_submission_events_at ON submission_events(at);
		CREATE INDEX IF NOT EXISTS idx_submission_events_round ON submission_events(round);
		CREATE INDEX IF NOT EXISTS idx_submission_events_team ON submission_events(team_id);
		CREATE INDEX IF NOT EXISTS idx_submission_events_reason ON submission_events(reason);
		CREATE INDEX IF NOT EXISTS idx_peer_samples_at ON peer_samples(at);
		CREATE INDEX IF NOT EXISTS idx_peer_samples_team ON peer_samples(team_id);
		CREATE INDEX IF NOT EXISTS idx_peer_samples_address ON peer_samples(address);
	`)
	if err != nil {
		log.Fatalf("Error creating indexs: %v", err)
	}

}

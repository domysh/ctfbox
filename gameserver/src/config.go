package main

import (
	"context"
	"database/sql"
	"encoding/json"
	"fmt"
	"game/db"
	"game/log"
	"os"
	"strconv"
	"strings"
	"time"

	"github.com/uptrace/bun"
)

type TeamInfo struct {
	ID    int     `json:"id"`
	Token *string `json:"token"`
	Name  string  `json:"name"`
	Image string  `json:"image"`
	Nop   bool    `json:"nop"`
}

type Config struct {
	RoundLen            time.Duration
	GraceDuration       time.Duration
	SubmitterLimitTime  time.Duration
	GameStartTime       time.Time
	GameEndTime         *time.Time
	FlagRegex           string
	Services            []string
	Round               int64      `json:"tick_time"`
	Token               string     `json:"gameserver_token"`
	Teams               []TeamInfo `json:"teams"`
	CheckerDir          string
	FlagExpireTicks     int64    `json:"flag_expire_ticks"`
	InitialServiceScore float64  `json:"initial_service_score"`
	SubmitterTimeout    *float64 `json:"submission_timeout"`
	MaxFlagsPerRequest  int      `json:"max_flags_per_request"`
	Debug               bool     `json:"debug"`
	StartTime           *string  `json:"start_time"`
	EndTime             *string  `json:"end_time"`
	GraceTime           *int64   `json:"grace_time"`
}

var conf *Config
var conn *bun.DB

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

func (c *Config) getTeamByID(teamID int) *TeamInfo {
	for _, teamInfo := range c.Teams {
		if teamID == teamInfo.ID {
			return &teamInfo
		}
	}
	return nil
}

func (c *Config) getTeamByToken(token string) *TeamInfo {
	for _, teamInfo := range c.Teams {
		if teamInfo.Token != nil && *teamInfo.Token == token {
			return &teamInfo
		}
	}
	return nil
}

func initScoreboard() {
	var ctx context.Context = context.Background()
	log.Debugf("Initializing scoreboard")

	for _, teamInfo := range conf.Teams {
		team := teamIDToIP(teamInfo.ID)
		for _, service := range conf.Services {
			fetchedScore := new(db.ServiceScore)
			err := conn.NewSelect().Model(fetchedScore).Where("team = ? and service = ?", team, service).Scan(ctx)
			if err != nil {
				if err == sql.ErrNoRows {
					_, err := conn.NewInsert().Model(&db.ServiceScore{
						Team:    team,
						Service: service,
						Score:   conf.InitialServiceScore,
						Offense: 0.0,
						Defense: 0.0,
					}).Exec(ctx)
					if err != nil {
						log.Panicf("Error inserting service score %v", err)
					}
				} else {
					log.Panicf("Error fetching service score %v", err)
				}
			}
		}
	}

}

func LoadConfig(path string) (*Config, error) {
	c := &Config{}

	if _, err := os.Stat(path); os.IsNotExist(err) {
		return c, err
	}
	file, err := os.Open(path)
	if err != nil {
		return c, err
	}
	defer file.Close()

	dec := json.NewDecoder(file)
	if err = dec.Decode(c); err != nil {
		return c, err
	}

	conf = c
	conf.FlagRegex = "[A-Z0-9]{31}="

	conf.RoundLen = time.Duration(conf.Round) * time.Second
	if conf.GraceTime != nil {
		conf.GraceDuration = time.Duration(*conf.GraceTime) * time.Second
	} else {
		conf.GraceDuration = 0
	}
	if conf.SubmitterTimeout != nil {
		conf.SubmitterLimitTime = time.Duration(*conf.SubmitterTimeout) * time.Second
	}

	// Init services data
	conf.Services = make([]string, 0)
	entries, err := os.ReadDir("../checkers")
	if err != nil {
		log.Fatal(err)
	}
	for _, e := range entries {
		if e.IsDir() {
			checkerPath := "../checkers/" + e.Name() + "/checker.py"
			if _, err := os.Stat(checkerPath); err == nil {
				conf.Services = append(conf.Services, e.Name())
			}
		}
	}

	if conf.Debug {
		log.SetLogLevel("debug")
	} else {
		log.SetLogLevel("info")
	}

	initRand()
	db.InitDB()
	conn = db.ConnectDB()
	initScoreboard()

	dbStartTime := db.GetStartTime()

	if dbStartTime == nil {
		if conf.StartTime != nil {
			startTime, err := time.Parse(time.RFC3339, *conf.StartTime)
			if err != nil {
				log.Panicf("Error parsing start time: %v", err)
			}
			db.SetStartTime(startTime)
		} else {
			db.SetStartTime(time.Now().UTC().Add(conf.GraceDuration))
		}
	}

	dbStartTime = db.GetStartTime()
	if dbStartTime == nil {
		log.Panicf("Error fetching start time from database")
	}

	conf.GameStartTime = *dbStartTime

	if conf.EndTime != nil {
		endTime, err := time.Parse(time.RFC3339, *conf.EndTime)
		if err != nil {
			log.Panicf("Error parsing end time: %v", err)
		}
		conf.GameEndTime = &endTime
	} else {
		conf.GameEndTime = nil
	}

	return conf, nil
}

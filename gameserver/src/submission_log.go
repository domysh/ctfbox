package main

import (
	"context"
	"strings"
	"sync/atomic"
	"time"

	"game/db"
	"game/log"
)

// Every submission attempt is logged, accepted or not: during a real game the
// interesting question is usually why a team's flags are being refused, and
// flag_submissions only knows about the ones that worked.
//
// Teams submit in bursts of hundreds of flags, so the write path never touches
// the database inline: events go through a buffered channel and are inserted in
// batches. If the buffer ever fills up the events are dropped rather than
// slowing down the submission endpoint, which is the one thing that must stay
// fast.

const (
	submissionQueueSize = 16384
	submissionBatchSize = 512
	submissionFlushTime = 500 * time.Millisecond
	submissionFlagMax   = 64
)

var (
	submissionQueue   = make(chan *db.SubmissionEvent, submissionQueueSize)
	submissionDropped atomic.Int64
)

func newSubmissionEvent(team *TeamState, flag string, round uint) *db.SubmissionEvent {
	ev := &db.SubmissionEvent{
		At:       time.Now(),
		Round:    int(round),
		TeamID:   -1,
		VictimID: -1,
		Flag:     truncate(strings.Trim(flag, " \n\t\r"), submissionFlagMax),
	}
	if team != nil {
		ev.Team = team.IP
		ev.TeamID = team.ID
	}
	return ev
}

func recordSubmission(ev *db.SubmissionEvent) {
	select {
	case submissionQueue <- ev:
	default:
		submissionDropped.Add(1)
	}
}

func startSubmissionLogger(retention time.Duration) {
	go func() {
		batch := make([]db.SubmissionEvent, 0, submissionBatchSize)
		ticker := time.NewTicker(submissionFlushTime)
		defer ticker.Stop()

		flush := func() {
			if len(batch) == 0 {
				return
			}
			if _, err := conn.NewInsert().Model(&batch).Exec(context.Background()); err != nil {
				log.Debugf("Error storing submission events: %v", err)
			}
			batch = batch[:0]
		}

		for {
			select {
			case ev := <-submissionQueue:
				batch = append(batch, *ev)
				if len(batch) >= submissionBatchSize {
					flush()
				}
			case <-ticker.C:
				flush()
				if dropped := submissionDropped.Swap(0); dropped > 0 {
					log.Warningf("Dropped %d submission events: the log cannot keep up", dropped)
				}
			}
		}
	}()

	// Same reasoning as the traffic samples: a long game on a busy submitter
	// would otherwise grow this table without bound.
	go func() {
		ticker := time.NewTicker(30 * time.Minute)
		defer ticker.Stop()
		for range ticker.C {
			if _, err := conn.NewDelete().Model((*db.SubmissionEvent)(nil)).
				Where("at < ?", time.Now().Add(-retention)).
				Exec(context.Background()); err != nil {
				log.Debugf("Error pruning submission events: %v", err)
			}
		}
	}()
}

package main

import (
	"container/heap"
	"context"
	"sync"
	"sync/atomic"
	"time"

	"game/db"
	"game/log"
)

// Job is one checker invocation. Jobs are produced by the round orchestrator
// and consumed by workers, either the embedded one or remote checker nodes.
type Job struct {
	ID      int64  `json:"id"`
	Round   uint   `json:"round"`
	TeamID  int    `json:"team_id"`
	TeamIP  string `json:"team_ip"`
	Service string `json:"service"`
	Action  string `json:"action"`
	Flag    string `json:"flag"`
	// Timeout is how long a worker may spend on this job, in seconds.
	Timeout int64 `json:"timeout"`

	// NotBefore spreads the checks over the round so that the players cannot
	// tell a checker connection from a real one by looking at the clock.
	NotBefore time.Time `json:"-"`
	Deadline  time.Time `json:"-"`

	result   chan JobResult
	attempts int
	index    int
}

// JobResult is what a worker reports back.
type JobResult struct {
	JobID      int64  `json:"job_id"`
	Status     int    `json:"status"`
	Message    string `json:"message"`
	Worker     string `json:"worker"`
	DurationMs int64  `json:"duration_ms"`
}

type jobHeap []*Job

func (h jobHeap) Len() int            { return len(h) }
func (h jobHeap) Less(i, j int) bool  { return h[i].NotBefore.Before(h[j].NotBefore) }
func (h jobHeap) Swap(i, j int)       { h[i], h[j] = h[j], h[i]; h[i].index = i; h[j].index = j }
func (h *jobHeap) Push(x interface{}) { job := x.(*Job); job.index = len(*h); *h = append(*h, job) }
func (h *jobHeap) Pop() interface{} {
	old := *h
	n := len(old)
	job := old[n-1]
	old[n-1] = nil
	*h = old[:n-1]
	return job
}

type leasedJob struct {
	job     *Job
	worker  string
	expires time.Time
}

// Dispatcher balances checker jobs across every registered worker. Workers pull
// work when they have free capacity, which is the simplest scheduler that
// naturally balances heterogeneous machines: a slow node just claims less.
type Dispatcher struct {
	mu       sync.Mutex
	pending  jobHeap
	inflight map[int64]*leasedJob
	nextID   int64
	closed   bool

	persist chan persistEvent
}

type persistEvent struct {
	job    *Job
	result *JobResult
	state  string
}

var dispatcher = newDispatcher()

func newDispatcher() *Dispatcher {
	d := &Dispatcher{
		inflight: make(map[int64]*leasedJob),
		persist:  make(chan persistEvent, 8192),
	}
	heap.Init(&d.pending)
	return d
}

// Submit enqueues a job and returns the channel the result will be delivered on.
func (d *Dispatcher) Submit(job *Job) chan JobResult {
	job.ID = atomic.AddInt64(&d.nextID, 1)
	job.result = make(chan JobResult, 1)
	if job.NotBefore.IsZero() {
		job.NotBefore = time.Now()
	}
	d.mu.Lock()
	heap.Push(&d.pending, job)
	d.mu.Unlock()

	select {
	case d.persist <- persistEvent{job: job, state: "queued"}:
	default: // never block the game on bookkeeping
	}
	return job.result
}

// Claim hands at most max ready jobs to a worker, waiting up to wait for work
// to show up (long polling keeps remote workers responsive without hammering
// the control node).
func (d *Dispatcher) Claim(worker string, max int, wait time.Duration) []*Job {
	if max <= 0 {
		return nil
	}
	deadline := time.Now().Add(wait)
	for {
		claimed := d.tryClaim(worker, max)
		if len(claimed) > 0 || time.Now().After(deadline) {
			return claimed
		}
		time.Sleep(100 * time.Millisecond)
	}
}

func (d *Dispatcher) tryClaim(worker string, max int) []*Job {
	now := time.Now()
	claimed := make([]*Job, 0, max)

	d.mu.Lock()
	defer d.mu.Unlock()
	for len(claimed) < max && d.pending.Len() > 0 {
		next := d.pending[0]
		if next.NotBefore.After(now) {
			break
		}
		heap.Pop(&d.pending)
		lease := time.Duration(next.Timeout)*time.Second + 15*time.Second
		expires := now.Add(lease)
		if !next.Deadline.IsZero() && expires.After(next.Deadline) {
			expires = next.Deadline
		}
		d.inflight[next.ID] = &leasedJob{job: next, worker: worker, expires: expires}
		claimed = append(claimed, next)
	}

	for _, job := range claimed {
		select {
		case d.persist <- persistEvent{job: job, state: "running"}:
		default:
		}
	}
	return claimed
}

// Complete resolves a job with the result reported by a worker.
func (d *Dispatcher) Complete(res JobResult) {
	d.mu.Lock()
	leased, ok := d.inflight[res.JobID]
	if ok {
		delete(d.inflight, res.JobID)
	}
	d.mu.Unlock()

	if !ok {
		log.Debugf("Result for unknown/expired job %v from %v", res.JobID, res.Worker)
		return
	}
	select {
	case leased.job.result <- res:
	default:
	}
	select {
	case d.persist <- persistEvent{job: leased.job, result: &res, state: "done"}:
	default:
	}
}

// fail resolves a job without a worker (timeout, lost worker, cancelled round).
func (d *Dispatcher) fail(job *Job, status int, message string) {
	res := JobResult{JobID: job.ID, Status: status, Message: message, Worker: ""}
	select {
	case job.result <- res:
	default:
	}
	select {
	case d.persist <- persistEvent{job: job, result: &res, state: "lost"}:
	default:
	}
}

// Reap requeues the jobs of workers that went away and kills the ones that ran
// past the end of their round.
func (d *Dispatcher) Reap() {
	now := time.Now()
	var requeue []*Job
	var expired []*Job

	d.mu.Lock()
	for id, leased := range d.inflight {
		if now.Before(leased.expires) {
			continue
		}
		delete(d.inflight, id)
		if !leased.job.Deadline.IsZero() && now.After(leased.job.Deadline) {
			expired = append(expired, leased.job)
			continue
		}
		if leased.job.attempts >= 2 {
			expired = append(expired, leased.job)
			continue
		}
		leased.job.attempts++
		requeue = append(requeue, leased.job)
	}
	// Drop pending jobs whose round is already over.
	kept := make(jobHeap, 0, d.pending.Len())
	for _, job := range d.pending {
		if !job.Deadline.IsZero() && now.After(job.Deadline) {
			expired = append(expired, job)
			continue
		}
		kept = append(kept, job)
	}
	if len(kept) != d.pending.Len() {
		d.pending = kept
		heap.Init(&d.pending)
	}
	for _, job := range requeue {
		job.NotBefore = now
		heap.Push(&d.pending, job)
	}
	d.mu.Unlock()

	for _, job := range expired {
		d.fail(job, KILLED, "Checker timeout (no worker completed the job in time)")
	}
	if len(requeue) > 0 {
		log.Warningf("Requeued %d checker jobs from lost workers", len(requeue))
	}
}

// Stats is what the admin panel shows about the queue.
type DispatcherStats struct {
	Pending int   `json:"pending"`
	Running int   `json:"running"`
	NextID  int64 `json:"last_job_id"`
}

func (d *Dispatcher) Stats() DispatcherStats {
	d.mu.Lock()
	defer d.mu.Unlock()
	return DispatcherStats{
		Pending: d.pending.Len(),
		Running: len(d.inflight),
		NextID:  atomic.LoadInt64(&d.nextID),
	}
}

// runPersister keeps the check_jobs table roughly in sync with the queue. It is
// best effort on purpose: bookkeeping must never slow the game down.
func (d *Dispatcher) runPersister() {
	conn := db.ConnectDB()
	ticker := time.NewTicker(500 * time.Millisecond)
	defer ticker.Stop()

	inserts := make([]*db.CheckJob, 0, 256)
	updates := make([]persistEvent, 0, 256)

	flush := func() {
		ctx := context.Background()
		if len(inserts) > 0 {
			if _, err := conn.NewInsert().Model(&inserts).Exec(ctx); err != nil {
				log.Debugf("Error persisting check jobs: %v", err)
			}
			inserts = inserts[:0]
		}
		for _, ev := range updates {
			q := conn.NewUpdate().Model((*db.CheckJob)(nil)).Where("id = ?", ev.job.ID).Set("state = ?", ev.state)
			switch ev.state {
			case "running":
				q = q.Set("started_at = ?", time.Now())
			default:
				if ev.result != nil {
					now := time.Now()
					q = q.Set("finished_at = ?", now).
						Set("status = ?", ev.result.Status).
						Set("message = ?", truncate(ev.result.Message, 512)).
						Set("worker = ?", ev.result.Worker).
						Set("duration_ms = ?", ev.result.DurationMs)
				}
			}
			if _, err := q.Exec(ctx); err != nil {
				log.Debugf("Error updating check job %v: %v", ev.job.ID, err)
			}
		}
		updates = updates[:0]
	}

	for {
		select {
		case ev := <-d.persist:
			if ev.state == "queued" {
				inserts = append(inserts, &db.CheckJob{
					ID:        ev.job.ID,
					Round:     ev.job.Round,
					TeamID:    ev.job.TeamID,
					Team:      ev.job.TeamIP,
					Service:   ev.job.Service,
					Action:    ev.job.Action,
					Flag:      ev.job.Flag,
					State:     "queued",
					CreatedAt: time.Now(),
				})
			} else {
				updates = append(updates, ev)
			}
			if len(inserts)+len(updates) >= 256 {
				flush()
			}
		case <-ticker.C:
			flush()
		}
	}
}

func truncate(s string, n int) string {
	if len(s) <= n {
		return s
	}
	return s[:n]
}

// pruneJobs keeps the check_jobs table bounded: only the last few rounds are
// interesting for live debugging.
func pruneJobs(currentRound uint, keep uint) {
	if currentRound <= keep {
		return
	}
	conn := db.ConnectDB()
	if _, err := conn.NewDelete().Model((*db.CheckJob)(nil)).
		Where("round < ?", currentRound-keep).Exec(context.Background()); err != nil {
		log.Debugf("Error pruning check jobs: %v", err)
	}
}

func startDispatcher() {
	go dispatcher.runPersister()
	go func() {
		ticker := time.NewTicker(time.Second)
		defer ticker.Stop()
		for range ticker.C {
			dispatcher.Reap()
		}
	}()
}

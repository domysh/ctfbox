package main

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strconv"
	"sync"
	"sync/atomic"
	"time"

	"game/log"
)

const workerProtocolVersion = "1"

// runChecker executes one checker script. It is the only place that knows how a
// checker is invoked, and it is shared by the embedded and the remote workers.
func runChecker(job *Job, ctx context.Context) (int, string) {
	cmd := exec.CommandContext(ctx, "python3", "checker.py")
	cmd.Env = append(os.Environ(),
		"TOKEN="+conf.Token,
		"ACTION="+job.Action,
		"TEAM_ID="+strconv.Itoa(job.TeamID),
		"TEAM_IP="+job.TeamIP,
		"ROUND="+strconv.FormatUint(uint64(job.Round), 10),
		"FLAG="+job.Flag,
		"SERVICE="+job.Service,
		"TERM=xterm",
		"CTFBOX_API="+checkerAPIBase(),
		fmt.Sprintf("PYTHONPATH=%s:%s", os.Getenv("PYTHONPATH"), "../"),
	)

	workingDir, err := filepath.Abs("../checkers/" + job.Service)
	if err != nil {
		log.Criticalf("Error resolving checker dir for %v on %v: %v", job.Action, job.Service, err)
		return CRITICAL, "Checker system error"
	}
	cmd.Dir = workingDir

	var outb, errb bytes.Buffer
	cmd.Stdout = &outb
	cmd.Stderr = &errb

	if err := cmd.Start(); err != nil {
		log.Criticalf("Error running checker %v %v on %v: %v", job.Action, job.TeamIP, job.Service, err)
		return CRITICAL, "Checker system error"
	}

	err = cmd.Wait()
	msg := outb.String()

	if err == nil {
		log.Criticalf("Checker %v %v on %v exited with status 0: checkers must exit with a status code", job.Action, job.TeamIP, job.Service)
		return CRITICAL, "Checker system error"
	}

	log.Debugf("Checker %v %v on %v stderr: %v", job.Action, job.TeamIP, job.Service, errb.String())

	exiterr, ok := err.(*exec.ExitError)
	if !ok {
		log.Criticalf("Error waiting for checker %v %v on %v: %v", job.Action, job.TeamIP, job.Service, err)
		return CRITICAL, "Checker system error"
	}

	var color string
	exitCode := exiterr.ExitCode()
	switch exitCode {
	case OK:
		color = log.GREEN
		msg = "Everything is ok"
	case DOWN:
		color = log.RED
	case ERROR:
		color = log.HIGH_RED
	case KILLED:
		color = log.PURPLE
		msg = "Checker timeout (killed, service is probably down)"
	default:
		log.Infof("Checker unknown status %v: %v from %v on %v", job.Action, exitCode, job.TeamIP, job.Service)
		return ERROR, msg
	}

	log.Infof("Checker status %v: %v%v%v from %v on %v", job.Action, color, exitCode, log.END, job.TeamIP, job.Service)
	return exitCode, msg
}

func checkerAPIBase() string {
	if base := os.Getenv("CTFBOX_API"); base != "" {
		return base
	}
	if processRole == "worker" && controlBaseURL != "" {
		return controlBaseURL + ":8081"
	}
	return "http://flagid:8081"
}

func executeJob(job *Job) JobResult {
	timeout := time.Duration(job.Timeout) * time.Second
	if timeout <= 0 {
		timeout = 30 * time.Second
	}
	if !job.Deadline.IsZero() {
		if until := time.Until(job.Deadline); until > 0 && until < timeout {
			timeout = until
		}
	}
	ctx, cancel := context.WithTimeout(context.Background(), timeout)
	defer cancel()

	started := time.Now()
	status, message := runChecker(job, ctx)
	return JobResult{
		JobID:      job.ID,
		Status:     status,
		Message:    message,
		DurationMs: time.Since(started).Milliseconds(),
	}
}

// ----------------------------------------------------------------------------
// embedded worker: keeps the single-machine deployment working with zero setup
// ----------------------------------------------------------------------------

func defaultConcurrency() int {
	if raw := os.Getenv("CTFBOX_CONCURRENCY"); raw != "" {
		if parsed, err := strconv.Atoi(raw); err == nil && parsed > 0 {
			return parsed
		}
	}
	if conf.CheckerConcurrency > 0 {
		return conf.CheckerConcurrency
	}
	// Checkers are network bound, so oversubscribe the CPUs generously.
	concurrency := runtime.NumCPU() * 8
	if concurrency < 16 {
		concurrency = 16
	}
	return concurrency
}

func startEmbeddedWorker() {
	capacity := defaultConcurrency()
	id := "embedded"
	// The name is the node name, plain: the panel already tags it "embedded",
	// and matching the topology by name is what tells the node monitor that
	// this machine is alive.
	registry.Register(&WorkerRegistration{
		ID:       id,
		Name:     processNode,
		Capacity: capacity,
		Embedded: true,
		Version:  workerProtocolVersion,
		Address:  "local",
	})
	log.Infof("Embedded checker worker started with concurrency %d", capacity)

	var running int32
	for i := 0; i < capacity; i++ {
		go func() {
			for {
				jobs := dispatcher.Claim(id, 1, 2*time.Second)
				if len(jobs) == 0 {
					continue
				}
				atomic.AddInt32(&running, 1)
				registry.SetRunning(id, int(atomic.LoadInt32(&running)))
				res := executeJob(jobs[0])
				res.Worker = processNode
				dispatcher.Complete(res)
				registry.Completed(id, res.Status)
				atomic.AddInt32(&running, -1)
				registry.SetRunning(id, int(atomic.LoadInt32(&running)))
			}
		}()
	}
}

// ----------------------------------------------------------------------------
// remote worker mode: `CTFBOX_ROLE=worker` on any machine of the cluster
// ----------------------------------------------------------------------------

type workerHelloRequest struct {
	Token    string   `json:"token"`
	Name     string   `json:"name"`
	Capacity int      `json:"capacity"`
	Version  string   `json:"version"`
	Services []string `json:"services"`
}

type workerHelloResponse struct {
	WorkerID string `json:"worker_id"`
	Round    int    `json:"round"`
}

type workerClaimRequest struct {
	Token    string `json:"token"`
	WorkerID string `json:"worker_id"`
	Max      int    `json:"max"`
}

type workerResultRequest struct {
	Token    string      `json:"token"`
	WorkerID string      `json:"worker_id"`
	Running  int         `json:"running"`
	Results  []JobResult `json:"results"`
}

type remoteWorker struct {
	base     string
	name     string
	capacity int
	id       string
	client   *http.Client

	mu      sync.Mutex
	running int
	results []JobResult
}

func (w *remoteWorker) post(path string, payload interface{}, out interface{}) error {
	body, err := json.Marshal(payload)
	if err != nil {
		return err
	}
	resp, err := w.client.Post(w.base+path, "application/json", bytes.NewReader(body))
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("%s returned %d", path, resp.StatusCode)
	}
	if out == nil {
		return nil
	}
	return json.NewDecoder(resp.Body).Decode(out)
}

func (w *remoteWorker) hello() error {
	services := discoverServices()
	var resp workerHelloResponse
	if err := w.post("/worker/hello", workerHelloRequest{
		Token:    conf.Token,
		Name:     w.name,
		Capacity: w.capacity,
		Version:  workerProtocolVersion,
		Services: services,
	}, &resp); err != nil {
		return err
	}
	w.id = resp.WorkerID
	log.Infof("Registered on control node as worker %v (%d slots, %d services)", w.id, w.capacity, len(services))
	return nil
}

func (w *remoteWorker) flushResults() {
	w.mu.Lock()
	pending := w.results
	w.results = nil
	running := w.running
	w.mu.Unlock()

	if len(pending) == 0 && running == 0 {
		return
	}
	if err := w.post("/worker/result", workerResultRequest{
		Token:    conf.Token,
		WorkerID: w.id,
		Running:  running,
		Results:  pending,
	}, nil); err != nil {
		log.Errorf("Error reporting results: %v", err)
		// Put them back, the control node will retry the job otherwise.
		w.mu.Lock()
		w.results = append(pending, w.results...)
		w.mu.Unlock()
	}
}

func runWorkerMode() {
	base := os.Getenv("CTFBOX_CONTROL")
	if base == "" {
		log.Fatalf("CTFBOX_CONTROL must point to the control node (e.g. http://10.10.0.1)")
	}
	controlBaseURL = base
	name := os.Getenv("CTFBOX_NODE")
	if name == "" {
		name, _ = os.Hostname()
	}
	processNode = name

	capacity := defaultConcurrency()
	w := &remoteWorker{
		base:     base + ":8082",
		name:     name,
		capacity: capacity,
		client:   &http.Client{Timeout: 60 * time.Second},
	}

	for {
		if err := w.hello(); err != nil {
			log.Errorf("Cannot reach control node (%v), retrying in 5s", err)
			time.Sleep(5 * time.Second)
			continue
		}
		break
	}

	go func() {
		ticker := time.NewTicker(2 * time.Second)
		defer ticker.Stop()
		for range ticker.C {
			w.flushResults()
		}
	}()

	slots := make(chan struct{}, capacity)
	for {
		w.mu.Lock()
		free := capacity - w.running
		w.mu.Unlock()
		if free <= 0 {
			time.Sleep(200 * time.Millisecond)
			continue
		}

		var jobs []*Job
		if err := w.post("/worker/claim", workerClaimRequest{
			Token:    conf.Token,
			WorkerID: w.id,
			Max:      free,
		}, &jobs); err != nil {
			log.Errorf("Error claiming jobs: %v", err)
			time.Sleep(2 * time.Second)
			if err := w.hello(); err != nil {
				log.Debugf("Re-registration failed: %v", err)
			}
			continue
		}
		if len(jobs) == 0 {
			continue
		}

		for _, job := range jobs {
			slots <- struct{}{}
			w.mu.Lock()
			w.running++
			w.mu.Unlock()
			go func(job *Job) {
				defer func() { <-slots }()
				res := executeJob(job)
				res.Worker = w.id
				w.mu.Lock()
				w.running--
				w.results = append(w.results, res)
				w.mu.Unlock()
			}(job)
		}
	}
}

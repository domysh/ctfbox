package main

import (
	"os"
	"os/signal"
	"strings"
	"syscall"
	"time"

	"game/db"
	"game/log"

	"github.com/uptrace/bun"
)

var conn *bun.DB

func main() {
	var err error

	conf, err = loadRawConfig(configPath)
	if err != nil {
		log.Fatalf("Error loading config: %v", err)
	}
	if conf.Debug {
		log.SetLogLevel("debug")
	} else {
		log.SetLogLevel("info")
	}

	if role := os.Getenv("CTFBOX_ROLE"); role != "" {
		processRole = role
	}
	if node := os.Getenv("CTFBOX_NODE"); node != "" {
		processNode = node
	}

	initRand()

	if processRole == "worker" {
		log.Infof("Starting CTFBox checker worker node %v", processNode)
		runWorkerMode()
		return
	}

	db.InitDB()
	conn = db.ConnectDB()

	InitState(conf)
	log.Infof("Control room reachable from the admin VPN profiles only (%v)", adminVPNNetwork)
	log.Debugf("Settings: %+v", gs.Settings())

	startDispatcher()
	startTrafficPruner(24 * time.Hour)
	startSubmissionLogger(24 * time.Hour)
	applyNetworkBans()
	if !strings.EqualFold(os.Getenv("CTFBOX_EMBEDDED_WORKER"), "0") {
		startEmbeddedWorker()
	} else {
		log.Warningf("Embedded worker disabled: the game will only run with remote checker nodes")
	}

	go serveFlagIDs()
	go serveSubmission()
	go serveScoreboard()
	go serveClusterAPI()
	go checkerRoutine()

	stop := make(chan os.Signal, 1)
	signal.Notify(stop, os.Interrupt)
	signal.Notify(stop, syscall.SIGTERM)
	signal.Notify(stop, syscall.SIGINT)
	signal.Notify(stop, syscall.SIGQUIT)
	log.Infof("Game Server is now running. Press CTRL-C to exit.")
	<-stop
}

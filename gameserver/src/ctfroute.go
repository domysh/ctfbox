package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"net"
	"net/http"
	"strings"
	"sync"
	"time"

	"game/log"

	"github.com/pkg/errors"
)

// ctfRouteCommand talks to the router container sitting next to us through the
// shared unix socket.
func ctfRouteCommand(cmd string) error {
	conn, err := net.Dial("unix", "/unixsk/ctfroute.sock")
	if err != nil {
		log.Debugf("Failed to connect to the ctf router: %v", err)
		return err
	}
	defer conn.Close()
	heloReceived := false
	for {
		response := make([]byte, 1024)
		read, err := conn.Read(response)
		if err != nil {
			log.Debugf("Failed to read response from the ctf router: %v", err)
			return err
		}
		if read > 0 {
			strippedResponse := strings.Trim(string(response[:read]), "\n ")
			if !heloReceived {
				if strippedResponse == "HELO" {
					heloReceived = true
					if _, err = conn.Write([]byte(cmd + "\n")); err != nil {
						log.Debugf("Failed to send data to the ctf router: %v", err)
						return err
					}
					log.Debugf("Sent %v CTF Route command", cmd)
				} else {
					log.Debugf("Failed to %v CTF Route (no HELO): '%s'", cmd, strippedResponse)
					return errors.New("unexpected response (no HELO)")
				}
			} else {
				if strippedResponse == "OK" {
					log.Debugf("CTF Route %v done", cmd)
					return nil
				}
				log.Debugf("Failed to %v CTF Route (unexpected response): '%s'", cmd, strippedResponse)
				return errors.New("unexpected response")
			}
		}
	}
}

var routerAgentClient = &http.Client{Timeout: 10 * time.Second}

// remoteRouterNodes are the vpn nodes of a distributed deployment that are not
// reachable through the local unix socket.
func remoteRouterNodes() []NodeInfo {
	nodes := make([]NodeInfo, 0)
	for _, node := range conf.Nodes {
		if node.Name == processNode {
			continue
		}
		if node.HasRole("vpn") || node.HasRole("router") {
			nodes = append(nodes, node)
		}
	}
	return nodes
}

// errNodeNotJoined means a router has not checked in yet, so there is no
// address to reach its agent at. It is not a failure: the router converges to
// the stored state on its first reconcile tick, which is what the check in is.
var errNodeNotJoined = errors.New("node has not joined the cluster yet")

func sendRouterAgentCommand(node NodeInfo, cmd string) error {
	payload, err := json.Marshal(map[string]string{"token": conf.Token, "cmd": cmd})
	if err != nil {
		return err
	}
	// The agent listens inside the game network only: its port is deliberately
	// not published, so the address a node checked in from is the only one that
	// can reach it. There is no fallback to the configured address — that one
	// is where the node lives on its own network, where nothing is listening.
	address := nodeRegistry.Address(node.Name)
	if address == "" {
		return fmt.Errorf("%s: %w", node.Name, errNodeNotJoined)
	}
	url := fmt.Sprintf("http://%s:8090/ctfroute", address)
	resp, err := routerAgentClient.Post(url, "application/json", bytes.NewReader(payload))
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("router node %s returned %d", node.Name, resp.StatusCode)
	}
	return nil
}

// ctfRouteBroadcast applies a network command on every router of the cluster.
func ctfRouteBroadcast(cmd string) error {
	localErr := ctfRouteCommand(strings.ToUpper(cmd))

	var wg sync.WaitGroup
	var mu sync.Mutex
	var failures []string
	var waiting []string
	for _, node := range remoteRouterNodes() {
		wg.Add(1)
		go func(node NodeInfo) {
			defer wg.Done()
			err := sendRouterAgentCommand(node, strings.ToLower(cmd))
			if err == nil {
				return
			}
			mu.Lock()
			defer mu.Unlock()
			if errors.Is(err, errNodeNotJoined) {
				waiting = append(waiting, node.Name)
				return
			}
			failures = append(failures, node.Name+": "+err.Error())
		}(node)
	}
	wg.Wait()

	// A node that has not joined yet is the normal state of a cluster coming
	// up, not something to shout about: it gets the state on its first check
	// in, which is exactly what the reconcile loop is for.
	if len(waiting) > 0 {
		log.Infof("%v not applied on %v yet: still waiting for them to join",
			cmd, strings.Join(waiting, ", "))
	}
	if len(failures) > 0 {
		log.Errorf("Network command %v failed on: %v", cmd, strings.Join(failures, ", "))
		return errors.New("network command failed on " + strings.Join(failures, ", "))
	}
	return localErr
}

// setNetworkTo records what the network is supposed to look like and then tries
// to make it so.
//
// The order matters: the desired state is stored even when the broadcast fails,
// because that state is what the routers converge to on their next check in. A
// node that was down, or that had not joined yet, would otherwise never learn
// the game had started.
func setNetworkTo(state string, command string) error {
	gs.setNetworkState(state)
	if err := ctfRouteBroadcast(command); err != nil {
		log.Warningf("Network is %v but some routers did not get it yet (%v), they will catch up", state, err)
		return err
	}
	log.Infof("Network %v", state)
	return nil
}

func CtfRouteUnlock() error { return setNetworkTo("unlocked", "UNLOCK") }

func CtfRouteLock() error { return setNetworkTo("locked", "LOCK") }

func CtfRouteFreeze() error { return setNetworkTo("frozen", "FREEZE") }

// CtfRouteBanTeam cuts a team off the game network on every router node.
func CtfRouteBanTeam(teamID int) error {
	return ctfRouteBroadcast(fmt.Sprintf("BAN %d", teamID))
}

func CtfRouteUnbanTeam(teamID int) error {
	return ctfRouteBroadcast(fmt.Sprintf("UNBAN %d", teamID))
}

// applyNetworkBans re-applies every ban after a router restart.
func applyNetworkBans() {
	for _, team := range gs.Teams() {
		if !team.NetworkBanned {
			continue
		}
		if err := CtfRouteBanTeam(team.ID); err != nil {
			log.Errorf("Error re-applying network ban for team %v: %v", team.ID, err)
		}
	}
}

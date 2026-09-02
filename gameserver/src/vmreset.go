package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"net/http"
	"strconv"
	"time"

	"game/log"

	"github.com/gorilla/mux"
)

/*
	Resetting a team box means cloning it again from the base image, which can
	only happen where the box lives: the incus container of the node hosting it.
	A small agent there does the work and this asks it to.

	Only boxes on the control node's own machine can be reset from the panel:
	the incus container of a remote node has no address inside the game network,
	so there is nothing to dial. When the box is elsewhere the answer says which
	node it is on and what to run there, which beats a button that silently does
	nothing.
*/

var vmAgentClient = &http.Client{Timeout: 20 * time.Second}

// vmNodeOfTeam is the node hosting a team's box, following the same assignment
// run.py wrote into the configuration.
func vmNodeOfTeam(teamID int) *NodeInfo {
	for index, node := range conf.Nodes {
		for _, hosted := range node.VMTeams {
			if hosted == teamID {
				return &conf.Nodes[index]
			}
		}
	}
	return nil
}

type vmResetResponse struct {
	Status string `json:"status"`
	Team   int    `json:"team"`
	Node   string `json:"node"`
}

func handleAdminResetVM(w http.ResponseWriter, r *http.Request) {
	teamID, err := strconv.Atoi(mux.Vars(r)["team_id"])
	if err != nil {
		http.Error(w, "Invalid team id", http.StatusBadRequest)
		return
	}
	team := gs.TeamByID(teamID)
	if team == nil {
		http.Error(w, "Unknown team", http.StatusNotFound)
		return
	}
	if conf.VMMode == "none" {
		http.Error(w,
			"vm_mode is 'none': the teams bring their own boxes, there is nothing to reset",
			http.StatusConflict)
		return
	}

	node := vmNodeOfTeam(teamID)
	nodeName := processNode
	if node != nil {
		nodeName = node.Name
	}
	if node != nil && node.Name != processNode {
		http.Error(w, fmt.Sprintf(
			"The box of team %d runs on node %q, which the control room cannot reach. "+
				"Run './run.py resetvm %d' from the machine you deploy with.",
			teamID, node.Name, teamID), http.StatusConflict)
		return
	}

	payload, err := json.Marshal(map[string]interface{}{
		"token": conf.Token,
		"team":  teamID,
	})
	if err != nil {
		http.Error(w, "Internal server error", http.StatusInternalServerError)
		return
	}
	resp, err := vmAgentClient.Post(
		"http://incus:8091/vm/reset", "application/json", bytes.NewReader(payload))
	if err != nil {
		log.Errorf("Cannot reach the incus agent: %v", err)
		http.Error(w,
			"Cannot reach the box manager of this node. It only answers once the "+
				"incus container is up; on a privileged deployment use './run.py resetvm'.",
			http.StatusBadGateway)
		return
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusAccepted {
		var answer map[string]interface{}
		message := "the box manager refused the reset"
		if json.NewDecoder(resp.Body).Decode(&answer) == nil {
			if text, ok := answer["error"].(string); ok && text != "" {
				message = text
			}
		}
		http.Error(w, message, resp.StatusCode)
		return
	}

	auditLog(adminActor(r), "team.reset-vm", strconv.Itoa(teamID), "node="+nodeName)
	log.Noticef("Box of team %d (%v) is being reset from the control room", teamID, team.Name)
	writeJSON(w, vmResetResponse{Status: "resetting", Team: teamID, Node: nodeName})
}

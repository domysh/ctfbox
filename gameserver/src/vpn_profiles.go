package main

import (
	"encoding/json"
	"net"
	"net/http"
	"strconv"
	"strings"

	"game/log"

	"github.com/gorilla/mux"
)

/*
	A VPN profile is one WireGuard peer, and one peer is one laptop. Suspending
	it cuts that laptop off the game network and leaves the rest of its team
	playing, which is what a network ban cannot do: that one takes the whole
	team out.

	The desired set is stored on the control node and every router converges to
	it on its reconcile tick, the same way it converges to the network state and
	the team bans. A router that restarts comes back with every peer its
	wg0.conf declares and drops the suspended ones again on its own.
*/

// profileAddress checks the address names a real profile before it is written
// anywhere: player profiles live at 10.80.<team>.<n>, the organizers' at
// 10.80.253.<n>.
func profileAddress(raw string) (string, bool) {
	address := strings.TrimSpace(raw)
	parsed := net.ParseIP(address)
	if parsed == nil || parsed.To4() == nil {
		return "", false
	}
	octets := parsed.To4()
	if octets[0] != 10 || octets[1] != 80 {
		return "", false
	}
	return parsed.To4().String(), true
}

// adminProfileSubnet is the third octet of the organizers' own profiles.
const adminProfileSubnet = 253

func teamOfProfile(address string) int {
	parsed := net.ParseIP(address)
	if parsed == nil || parsed.To4() == nil {
		return -1
	}
	third := int(parsed.To4()[2])
	if third == adminProfileSubnet {
		return -1
	}
	return third
}

type vpnProfileView struct {
	Address   string `json:"address"`
	TeamID    int    `json:"team_id"`
	Profile   int    `json:"profile"`
	Suspended bool   `json:"suspended"`
	Admin     bool   `json:"admin"`
}

// handleAdminVPNProfiles lists what is currently suspended. The profiles
// themselves are enumerated by the monitoring endpoint, which knows their
// traffic; this one is the authority on what is cut off.
func handleAdminVPNProfiles(w http.ResponseWriter, r *http.Request) {
	suspended := gs.SuspendedProfiles()
	out := make([]vpnProfileView, 0, len(suspended))
	for _, address := range suspended {
		team := teamOfProfile(address)
		profile := 0
		if parsed := net.ParseIP(address); parsed != nil && parsed.To4() != nil {
			profile = int(parsed.To4()[3])
		}
		out = append(out, vpnProfileView{
			Address:   address,
			TeamID:    team,
			Profile:   profile,
			Suspended: true,
			Admin:     team < 0,
		})
	}
	writeJSON(w, map[string]interface{}{"suspended": out})
}

func handleAdminSuspendProfile(w http.ResponseWriter, r *http.Request) {
	address, ok := profileAddress(mux.Vars(r)["address"])
	if !ok {
		http.Error(w, "Not a VPN profile address", http.StatusBadRequest)
		return
	}

	var body struct {
		Suspended bool `json:"suspended"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		http.Error(w, "Invalid body", http.StatusBadRequest)
		return
	}

	// Cutting off the profile you are connected through would lock you out of
	// the control room with no way back in but a terminal on the server.
	if body.Suspended && peerIP(r) != nil && address == peerIP(r).String() {
		http.Error(w,
			"That is the profile you are connected through: suspending it would lock you out",
			http.StatusConflict)
		return
	}

	gs.SetProfileSuspended(address, body.Suspended)

	action := "vpn.resume"
	if body.Suspended {
		action = "vpn.suspend"
	}
	team := teamOfProfile(address)
	detail := "team=" + strconv.Itoa(team)
	if team < 0 {
		detail = "admin profile"
	}
	auditLog(adminActor(r), action, address, detail)
	log.Noticef("VPN profile %v is now %v", address, map[bool]string{
		true: "suspended", false: "active"}[body.Suspended])

	// The routers pick this up on their next reconcile tick, but nudging them
	// now makes the panel feel like it did something.
	go func() {
		if err := ctfRouteBroadcast("status"); err != nil {
			log.Debugf("Could not nudge the routers after a profile change: %v", err)
		}
	}()

	writeJSON(w, vpnProfileView{
		Address:   address,
		TeamID:    team,
		Profile:   int(net.ParseIP(address).To4()[3]),
		Suspended: body.Suspended,
		Admin:     team < 0,
	})
}

package main

import (
	"bufio"
	"bytes"
	"encoding/binary"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"sort"
	"strconv"
	"strings"
	"sync"
	"time"

	"game/log"
)

/*
	Packet capture lives on the routers, which are the only machines the game
	traffic actually crosses. The control node never stores a copy: it asks each
	router for the slice the organizers want and streams the answer straight
	through, so a four hour capture never has to fit anywhere.

	Slices are addressed by time. Rounds and "the last N minutes" are turned
	into a time range here, because the routers know nothing about rounds.
*/

// pcapClient has no timeout on purpose: a download of a wide range legitimately
// takes minutes, and the transfer is streamed, so a stalled node shows up as a
// stalled stream rather than as a truncated file.
var pcapClient = &http.Client{Timeout: 0}

type pcapNode struct {
	Name string
	URL  string
}

// routerNodesForPcap lists every router of the deployment with the address to
// reach its agent at. The local router is a compose service, the remote ones
// answer on the address they checked in from.
func routerNodesForPcap() []pcapNode {
	nodes := make([]pcapNode, 0)
	for _, node := range conf.Nodes {
		if !node.HasRole("vpn") && !node.HasRole("router") {
			continue
		}
		if node.Name == processNode {
			nodes = append(nodes, pcapNode{Name: node.Name, URL: "http://router:8090"})
			continue
		}
		// Same as the ctfroute agent: only the address the node checked in
		// from can reach it, the configured one has nothing listening.
		address := nodeRegistry.Address(node.Name)
		if address == "" {
			log.Debugf("Skipping the capture of %v: it has not joined yet", node.Name)
			continue
		}
		nodes = append(nodes, pcapNode{Name: node.Name, URL: "http://" + address + ":8090"})
	}
	if len(nodes) == 0 {
		// Single machine: no topology declared, one router next door.
		nodes = append(nodes, pcapNode{Name: processNode, URL: "http://router:8090"})
	}
	sort.Slice(nodes, func(i, j int) bool { return nodes[i].Name < nodes[j].Name })
	return nodes
}

type pcapNodeStatus struct {
	Node          string   `json:"node"`
	Enabled       bool     `json:"enabled"`
	Interface     string   `json:"interface"`
	Files         int      `json:"files"`
	Bytes         int64    `json:"bytes"`
	MaxBytes      int64    `json:"max_bytes"`
	RotateSeconds int      `json:"rotate_seconds"`
	Oldest        *float64 `json:"oldest"`
	Newest        *float64 `json:"newest"`
	FreeBytes     *int64   `json:"free_bytes"`
	Error         string   `json:"error,omitempty"`
}

func handleAdminPcapStatus(w http.ResponseWriter, r *http.Request) {
	nodes := routerNodesForPcap()
	results := make([]pcapNodeStatus, len(nodes))

	var wg sync.WaitGroup
	for index, node := range nodes {
		wg.Add(1)
		go func(index int, node pcapNode) {
			defer wg.Done()
			status := pcapNodeStatus{Node: node.Name}
			req, err := http.NewRequest("GET", node.URL+"/pcap/status", nil)
			if err != nil {
				status.Error = err.Error()
				results[index] = status
				return
			}
			req.Header.Set("X-Token", conf.Token)
			client := &http.Client{Timeout: 10 * time.Second}
			resp, err := client.Do(req)
			if err != nil {
				status.Error = err.Error()
				results[index] = status
				return
			}
			defer resp.Body.Close()
			if resp.StatusCode != http.StatusOK {
				status.Error = fmt.Sprintf("agent returned %d", resp.StatusCode)
				results[index] = status
				return
			}
			if err := json.NewDecoder(resp.Body).Decode(&status); err != nil {
				status.Error = err.Error()
			}
			status.Node = node.Name
			results[index] = status
		}(index, node)
	}
	wg.Wait()

	total := int64(0)
	anyEnabled := false
	for _, status := range results {
		total += status.Bytes
		anyEnabled = anyEnabled || status.Enabled
	}
	writeJSON(w, map[string]interface{}{
		"enabled": anyEnabled,
		"bytes":   total,
		"nodes":   results,
	})
}

// pcapRange turns whatever the organizers asked for into an absolute time
// range. Everything is optional: no bound at all means the whole capture.
func pcapRange(r *http.Request) (start *float64, end *float64) {
	q := r.URL.Query()

	unix := func(name string) *float64 {
		raw := q.Get(name)
		if raw == "" {
			return nil
		}
		if parsed, err := strconv.ParseFloat(raw, 64); err == nil {
			return &parsed
		}
		if parsed, err := time.Parse(time.RFC3339, raw); err == nil {
			seconds := float64(parsed.UnixNano()) / 1e9
			return &seconds
		}
		return nil
	}

	start, end = unix("from"), unix("to")

	// Rounds win over raw timestamps: they are the way an organizer actually
	// thinks about "when did this happen".
	if raw := q.Get("from_round"); raw != "" {
		if round, err := strconv.Atoi(raw); err == nil && round >= 0 {
			at := float64(calcRoundStartTime(uint(round)).UnixNano()) / 1e9
			start = &at
		}
	}
	if raw := q.Get("to_round"); raw != "" {
		if round, err := strconv.Atoi(raw); err == nil && round >= 0 {
			// Inclusive: the end of the last round the organizer named.
			at := float64(calcRoundStartTime(uint(round+1)).UnixNano()) / 1e9
			end = &at
		}
	}
	if raw := q.Get("minutes"); raw != "" {
		if minutes, err := strconv.Atoi(raw); err == nil && minutes > 0 {
			at := float64(time.Now().Add(-time.Duration(minutes)*time.Minute).UnixNano()) / 1e9
			start = &at
			end = nil
		}
	}
	return start, end
}

func pcapNodeQuery(r *http.Request, start, end *float64) string {
	params := make([]string, 0, 4)
	if start != nil {
		params = append(params, fmt.Sprintf("from=%.3f", *start))
	}
	if end != nil {
		params = append(params, fmt.Sprintf("to=%.3f", *end))
	}
	if teams := r.URL.Query().Get("teams"); teams != "" {
		params = append(params, "teams="+teams)
	}
	if filter := r.URL.Query().Get("filter"); filter != "" {
		params = append(params, "filter="+filter)
	}
	if len(params) == 0 {
		return ""
	}
	return "?" + strings.Join(params, "&")
}

func fetchNodePcap(node pcapNode, query string) (io.ReadCloser, error) {
	req, err := http.NewRequest("GET", node.URL+"/pcap/download"+query, nil)
	if err != nil {
		return nil, err
	}
	req.Header.Set("X-Token", conf.Token)
	resp, err := pcapClient.Do(req)
	if err != nil {
		return nil, err
	}
	if resp.StatusCode != http.StatusOK {
		resp.Body.Close()
		return nil, fmt.Errorf("node %s returned %d", node.Name, resp.StatusCode)
	}
	return resp.Body, nil
}

// ----------------------------------------------------------------------------
// merging the nodes into one capture
// ----------------------------------------------------------------------------
//
// Every router answers with its own pcap. The organizers want one file, in
// chronological order, so the streams are merged here rather than left to the
// analyst: it is a k-way merge on the packet timestamp, one pending packet per
// node held in memory, so a four hour capture costs the same as a four second
// one.

const (
	pcapGlobalHeaderLen = 24
	pcapRecordHeaderLen = 16
)

type pcapStream struct {
	node   string
	body   io.ReadCloser
	reader *bufio.Reader

	endian    binary.ByteOrder
	ticks     uint64 // fraction units per second: 1e6 (usec) or 1e9 (nsec)
	linkType  uint32
	snapLen   uint32
	rawHeader []byte // the node's own global header, verbatim

	// The packet waiting to be written, if any.
	when    uint64 // nanoseconds since the epoch, so streams compare directly
	seconds uint32
	micros  uint32
	capLen  uint32
	origLen uint32
	payload []byte
	ok      bool
}

// openPcapStream reads the global header, which is what tells us whether the
// node has anything to say at all.
func openPcapStream(node string, body io.ReadCloser) (*pcapStream, error) {
	reader := bufio.NewReaderSize(body, 1<<16)
	header := make([]byte, pcapGlobalHeaderLen)
	if _, err := io.ReadFull(reader, header); err != nil {
		return nil, err
	}
	stream := &pcapStream{node: node, body: body, reader: reader}
	switch {
	case bytes.Equal(header[:4], []byte{0xd4, 0xc3, 0xb2, 0xa1}):
		stream.endian, stream.ticks = binary.LittleEndian, 1_000_000
	case bytes.Equal(header[:4], []byte{0xa1, 0xb2, 0xc3, 0xd4}):
		stream.endian, stream.ticks = binary.BigEndian, 1_000_000
	case bytes.Equal(header[:4], []byte{0x4d, 0x3c, 0xb2, 0xa1}):
		stream.endian, stream.ticks = binary.LittleEndian, 1_000_000_000
	case bytes.Equal(header[:4], []byte{0xa1, 0xb2, 0x3c, 0x4d}):
		stream.endian, stream.ticks = binary.BigEndian, 1_000_000_000
	default:
		return nil, fmt.Errorf("node %s did not answer with a pcap", node)
	}
	stream.snapLen = stream.endian.Uint32(header[16:20])
	stream.linkType = stream.endian.Uint32(header[20:24])
	stream.rawHeader = header
	return stream, nil
}

// next loads the following packet, or marks the stream exhausted. A truncated
// tail is not an error: the newest capture file is the one tcpdump is writing
// into right now.
func (s *pcapStream) next() {
	s.ok = false
	header := make([]byte, pcapRecordHeaderLen)
	if _, err := io.ReadFull(s.reader, header); err != nil {
		return
	}
	seconds := uint64(s.endian.Uint32(header[0:4]))
	fraction := uint64(s.endian.Uint32(header[4:8]))
	s.capLen = s.endian.Uint32(header[8:12])
	s.origLen = s.endian.Uint32(header[12:16])
	if s.capLen > 1<<24 { // a sane cap: never trust a length into an allocation
		return
	}
	payload := make([]byte, s.capLen)
	if _, err := io.ReadFull(s.reader, payload); err != nil {
		return
	}
	s.payload = payload
	s.seconds = uint32(seconds)
	s.micros = uint32(fraction * 1_000_000 / s.ticks)
	s.when = seconds*1_000_000_000 + fraction*(1_000_000_000/s.ticks)
	s.ok = true
}

func (s *pcapStream) close() {
	s.body.Close()
}

// handleAdminPcapDownload streams the requested slice as one capture file, with
// the packets of every router interleaved in timestamp order.
func handleAdminPcapDownload(w http.ResponseWriter, r *http.Request) {
	start, end := pcapRange(r)
	query := pcapNodeQuery(r, start, end)
	nodes := routerNodesForPcap()
	stamp := time.Now().Format("20060102-150405")

	auditLog(adminActor(r), "pcap.download", "", strings.TrimPrefix(query, "?"))

	// This response is the one place where the API's 60 second write deadline
	// is wrong: a wide slice of a busy game legitimately takes minutes, and
	// being cut off halfway hands the organizer a truncated capture that looks
	// like the server froze. The deadline is dropped for this response only.
	if err := http.NewResponseController(w).SetWriteDeadline(time.Time{}); err != nil {
		log.Debugf("Cannot lift the write deadline for the capture: %v", err)
	}

	streams := make([]*pcapStream, 0, len(nodes))
	for _, node := range nodes {
		body, err := fetchNodePcap(node, query)
		if err != nil {
			log.Warningf("Skipping capture of %v: %v", node.Name, err)
			continue
		}
		stream, err := openPcapStream(node.Name, body)
		if err != nil {
			log.Warningf("Skipping capture of %v: %v", node.Name, err)
			body.Close()
			continue
		}
		streams = append(streams, stream)
	}
	if len(streams) == 0 {
		http.Error(w, "no router returned a capture", http.StatusBadGateway)
		return
	}
	defer func() {
		for _, stream := range streams {
			stream.close()
		}
	}()

	// Every router captures the same kind of interface, so the link type is
	// the same everywhere. If a node ever disagrees its packets would be
	// decoded as something they are not, so it is left out rather than
	// silently corrupting the file.
	linkType := streams[0].linkType
	snapLen := uint32(0)
	kept := streams[:0]
	for _, stream := range streams {
		if stream.linkType != linkType {
			log.Warningf("Skipping capture of %v: link type %d, expected %d",
				stream.node, stream.linkType, linkType)
			continue
		}
		if stream.snapLen > snapLen {
			snapLen = stream.snapLen
		}
		kept = append(kept, stream)
	}
	streams = kept
	if snapLen == 0 {
		snapLen = 262144
	}

	w.Header().Set("Content-Type", "application/vnd.tcpdump.pcap")
	w.Header().Set("Content-Disposition",
		fmt.Sprintf(`attachment; filename="ctfbox-%s.pcap"`, stamp))

	out := bufio.NewWriterSize(w, 1<<16)
	defer out.Flush()

	// A single router needs no merging at all, which is the case on every
	// deployment that runs on one machine: pass its capture straight through
	// instead of decoding every packet only to write it back unchanged.
	if len(streams) == 1 {
		if _, err := out.Write(streams[0].rawHeader); err != nil {
			return
		}
		if _, err := io.Copy(out, streams[0].reader); err != nil {
			log.Debugf("Capture download interrupted: %v", err)
		}
		return
	}

	packets, err := mergePcapStreams(out, streams, linkType, snapLen)
	if err != nil {
		log.Debugf("Capture download interrupted: %v", err)
		return
	}
	log.Debugf("Served %d packets merged from %d routers", packets, len(streams))
}

// mergePcapStreams writes one capture holding every stream's packets in
// timestamp order. Only one packet per stream is ever held in memory, so the
// cost does not depend on how much traffic was asked for.
func mergePcapStreams(out io.Writer, streams []*pcapStream,
	linkType uint32, snapLen uint32) (int, error) {
	header := make([]byte, pcapGlobalHeaderLen)
	binary.LittleEndian.PutUint32(header[0:4], 0xa1b2c3d4)
	binary.LittleEndian.PutUint16(header[4:6], 2)
	binary.LittleEndian.PutUint16(header[6:8], 4)
	binary.LittleEndian.PutUint32(header[16:20], snapLen)
	binary.LittleEndian.PutUint32(header[20:24], linkType)
	if _, err := out.Write(header); err != nil {
		return 0, err
	}

	for _, stream := range streams {
		stream.next()
	}

	record := make([]byte, pcapRecordHeaderLen)
	packets := 0
	for {
		var oldest *pcapStream
		for _, stream := range streams {
			if stream.ok && (oldest == nil || stream.when < oldest.when) {
				oldest = stream
			}
		}
		if oldest == nil {
			return packets, nil
		}
		binary.LittleEndian.PutUint32(record[0:4], oldest.seconds)
		binary.LittleEndian.PutUint32(record[4:8], oldest.micros)
		binary.LittleEndian.PutUint32(record[8:12], oldest.capLen)
		binary.LittleEndian.PutUint32(record[12:16], oldest.origLen)
		if _, err := out.Write(record); err != nil {
			return packets, err
		}
		if _, err := out.Write(oldest.payload); err != nil {
			return packets, err
		}
		packets++
		oldest.next()
	}
}

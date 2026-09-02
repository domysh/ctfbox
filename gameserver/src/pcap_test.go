package main

import (
	"bytes"
	"encoding/binary"
	"io"
	"testing"
)

// moment is a packet timestamp, kept as whole microseconds so the test never
// compares floats that a decimal literal cannot represent exactly.
type moment struct {
	seconds uint32
	micros  uint32
}

// buildPcap makes a little endian microsecond capture holding the given
// timestamps, one byte of payload each, which is all the merger looks at.
func buildPcap(linkType uint32, moments []moment) []byte {
	out := &bytes.Buffer{}
	header := make([]byte, pcapGlobalHeaderLen)
	binary.LittleEndian.PutUint32(header[0:4], 0xa1b2c3d4)
	binary.LittleEndian.PutUint16(header[4:6], 2)
	binary.LittleEndian.PutUint16(header[6:8], 4)
	binary.LittleEndian.PutUint32(header[16:20], 262144)
	binary.LittleEndian.PutUint32(header[20:24], linkType)
	out.Write(header)
	for index, at := range moments {
		record := make([]byte, pcapRecordHeaderLen)
		binary.LittleEndian.PutUint32(record[0:4], at.seconds)
		binary.LittleEndian.PutUint32(record[4:8], at.micros)
		binary.LittleEndian.PutUint32(record[8:12], 1)
		binary.LittleEndian.PutUint32(record[12:16], 1)
		out.Write(record)
		out.Write([]byte{byte(index)})
	}
	return out.Bytes()
}

func readMoments(t *testing.T, data []byte) []moment {
	t.Helper()
	if len(data) < pcapGlobalHeaderLen {
		t.Fatalf("no global header")
	}
	moments := make([]moment, 0)
	for offset := pcapGlobalHeaderLen; offset+pcapRecordHeaderLen <= len(data); {
		seconds := binary.LittleEndian.Uint32(data[offset : offset+4])
		micros := binary.LittleEndian.Uint32(data[offset+4 : offset+8])
		length := binary.LittleEndian.Uint32(data[offset+8 : offset+12])
		moments = append(moments, moment{seconds, micros})
		offset += pcapRecordHeaderLen + int(length)
	}
	return moments
}

func openTestStream(t *testing.T, name string, data []byte) *pcapStream {
	t.Helper()
	stream, err := openPcapStream(name, io.NopCloser(bytes.NewReader(data)))
	if err != nil {
		t.Fatalf("openPcapStream(%s): %v", name, err)
	}
	return stream
}

// Two routers see different halves of the game; the download has to read as one
// capture, in time order, with nothing lost.
func TestMergePcapStreamsInterleaves(t *testing.T) {
	front := openTestStream(t, "front", buildPcap(101, []moment{
		{10, 0}, {12, 500_000}, {12, 750_000}, {30, 0},
	}))
	edge := openTestStream(t, "edge", buildPcap(101, []moment{
		{11, 0}, {12, 600_000}, {40, 0},
	}))

	out := &bytes.Buffer{}
	packets, err := mergePcapStreams(out, []*pcapStream{front, edge}, 101, 262144)
	if err != nil {
		t.Fatalf("merge: %v", err)
	}
	if packets != 7 {
		t.Fatalf("merged %d packets, want 7", packets)
	}
	got := readMoments(t, out.Bytes())
	want := []moment{
		{10, 0}, {11, 0}, {12, 500_000}, {12, 600_000}, {12, 750_000}, {30, 0}, {40, 0},
	}
	if len(got) != len(want) {
		t.Fatalf("got %d records, want %d", len(got), len(want))
	}
	for index := range want {
		if got[index] != want[index] {
			t.Fatalf("record %d is %v, want %v (full: %v)", index, got[index], want[index], got)
		}
	}
}

// A router with nothing to say must not hold up the others, and an exhausted
// stream must not be picked again.
func TestMergePcapStreamsWithEmptyNode(t *testing.T) {
	front := openTestStream(t, "front", buildPcap(101, []moment{{5, 0}, {6, 0}}))
	empty := openTestStream(t, "empty", buildPcap(101, nil))

	out := &bytes.Buffer{}
	packets, err := mergePcapStreams(out, []*pcapStream{empty, front}, 101, 262144)
	if err != nil {
		t.Fatalf("merge: %v", err)
	}
	if packets != 2 {
		t.Fatalf("merged %d packets, want 2", packets)
	}
	if got := readMoments(t, out.Bytes()); len(got) != 2 ||
		got[0] != (moment{5, 0}) || got[1] != (moment{6, 0}) {
		t.Fatalf("unexpected records: %v", got)
	}
}

// A capture cut off mid packet (the file tcpdump is writing into right now)
// must end the stream cleanly instead of emitting garbage.
func TestMergePcapStreamsTruncatedTail(t *testing.T) {
	full := buildPcap(101, []moment{{1, 0}, {2, 0}, {3, 0}})
	truncated := full[:len(full)-10]

	out := &bytes.Buffer{}
	packets, err := mergePcapStreams(out,
		[]*pcapStream{openTestStream(t, "cut", truncated)}, 101, 262144)
	if err != nil {
		t.Fatalf("merge: %v", err)
	}
	if packets != 2 {
		t.Fatalf("merged %d packets, want 2 (the third is truncated)", packets)
	}
}

// The merger has to read what the routers actually write, whatever endianness
// and resolution their libpcap uses.
func TestOpenPcapStreamRejectsGarbage(t *testing.T) {
	if _, err := openPcapStream("bad", io.NopCloser(bytes.NewReader(
		[]byte("this is not a capture at all")))); err == nil {
		t.Fatalf("a non pcap body was accepted")
	}
}

func TestPcapStreamNanosecondResolution(t *testing.T) {
	data := buildPcap(101, []moment{{7, 500_000}})
	// Same records, but flagged as nanosecond resolution.
	copy(data[0:4], []byte{0x4d, 0x3c, 0xb2, 0xa1})
	stream := openTestStream(t, "nano", data)
	stream.next()
	if !stream.ok {
		t.Fatalf("no packet read")
	}
	// 500000 fraction units at nanosecond resolution is half a millisecond.
	if stream.micros != 500 {
		t.Fatalf("micros = %d, want 500", stream.micros)
	}
	if stream.when != 7*1_000_000_000+500_000 {
		t.Fatalf("when = %d, want %d", stream.when, 7*1_000_000_000+500_000)
	}
}

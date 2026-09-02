package main

import (
	"compress/gzip"
	"io"
	"net/http"
	"strings"
)

// Struttura per implementare io.WriteCloser che supporta la compressione gzip
type gzipResponseWriter struct {
	io.Writer
	http.ResponseWriter
}

// Sovrascrive il metodo Write per scrivere dati compressi
func (w gzipResponseWriter) Write(b []byte) (int, error) {
	return w.Writer.Write(b)
}

// Unwrap lets http.NewResponseController reach the real ResponseWriter, so a
// handler can still take control of its own write deadline through the wrapper.
func (w gzipResponseWriter) Unwrap() http.ResponseWriter {
	return w.ResponseWriter
}

// Endpoints that stream a large binary body of their own. Gzipping a packet
// capture burns CPU on data that barely compresses, and the gzip writer holds
// the stream in its buffer, which is exactly what a streamed download must not
// do.
func streamsRawBody(path string) bool {
	return strings.HasPrefix(path, "/api/admin/pcap/download")
}

// Crea un middleware che applica la compressione gzip alle risposte
func compressMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		// Verifica se il client supporta la compressione gzip
		if !strings.Contains(r.Header.Get("Accept-Encoding"), "gzip") ||
			streamsRawBody(r.URL.Path) {
			next.ServeHTTP(w, r)
			return
		}

		// Configura la risposta compressa
		w.Header().Set("Content-Encoding", "gzip")
		gz := gzip.NewWriter(w)
		defer gz.Close()

		// Crea un wrapper per il ResponseWriter
		wrappedWriter := gzipResponseWriter{
			Writer:         gz,
			ResponseWriter: w,
		}

		// Serve la richiesta con lo writer compresso
		next.ServeHTTP(wrappedWriter, r)
	})
}

"""Expõe um MCPServer existente via HTTP + SSE — o segundo transporte oficial
do MCP (além de stdio), pensado para servidores remotos.

Reaproveita a lógica de qualquer `MCPServer` já existente (aqui, o
`ServidorClima` original) por composição: o handler HTTP apenas traduz
`tools/list` e `tools/call` para GET/POST reais, e usa Server-Sent Events
(`/eventos`) para o servidor empurrar atualizações ao cliente — algo que um
request/response HTTP comum não oferece nativamente.
"""

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def _criar_handler(mcp_server, eventos_geradores):
    class MCPHTTPHandler(BaseHTTPRequestHandler):
        def log_message(self, formato, *args):
            pass  # silencia o log padrão do http.server no stdout da demo

        def do_GET(self):
            if self.path == "/tools/list":
                self._responder_json(200, mcp_server.listar_tools())
            elif self.path == "/eventos":
                self._transmitir_sse()
            else:
                self._responder_json(404, {"erro": "rota não encontrada"})

        def do_POST(self):
            if self.path == "/tools/call":
                tamanho = int(self.headers.get("Content-Length", 0))
                corpo = json.loads(self.rfile.read(tamanho) or b"{}")
                resultado = mcp_server.chamar_tool(corpo.get("tool"), corpo.get("args", {}))
                self._responder_json(200, resultado)
            else:
                self._responder_json(404, {"erro": "rota não encontrada"})

        def _responder_json(self, status, dados):
            corpo = json.dumps(dados, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(corpo)))
            self.end_headers()
            self.wfile.write(corpo)

        def _transmitir_sse(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.end_headers()
            try:
                for evento in eventos_geradores(mcp_server):
                    linha = f"data: {json.dumps(evento, ensure_ascii=False)}\n\n"
                    self.wfile.write(linha.encode("utf-8"))
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
                pass

    return MCPHTTPHandler


def iniciar_servidor_http(mcp_server, host="127.0.0.1", port=8765, eventos_geradores=None):
    """Sobe um servidor HTTP real (ThreadingHTTPServer) numa thread daemon."""
    handler = _criar_handler(mcp_server, eventos_geradores or (lambda _s: iter(())))
    httpd = ThreadingHTTPServer((host, port), handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd, thread


def gerar_eventos_clima(servidor_clima, localizacao="Alegrete, RS", intervalo=2.0, quantidade=3):
    """Gera atualizações periódicas de previsão para o stream SSE do servidor de clima."""
    for _ in range(quantidade):
        time.sleep(intervalo)
        previsao = servidor_clima.chamar_tool(
            "obter_previsao", {"localizacao": localizacao, "dias": 1}
        )
        yield {"tipo": "atualizacao_clima", **previsao}

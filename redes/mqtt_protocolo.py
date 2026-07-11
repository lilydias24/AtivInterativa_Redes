"""Implementação mínima do protocolo MQTT 3.1.1 (subset QoS 0) sobre sockets TCP crus.

Cobre os pacotes necessários para o cenário da fazenda: CONNECT/CONNACK,
SUBSCRIBE/SUBACK, PUBLISH, PINGREQ/PINGRESP e DISCONNECT — o suficiente para um
sensor publicar leituras e um servidor MCP assinar o tópico, seguindo o
formato de pacotes definido pela especificação OASIS MQTT Version 3.1.1
(cabeçalho fixo + remaining length + variable header + payload).

Não usa nenhuma biblioteca de terceiros (ex.: paho-mqtt): os pacotes são
montados e interpretados byte a byte com `struct`, e o transporte é um
`socket.socket` TCP comum — o mesmo tipo de socket usado por um broker MQTT
real como o Mosquitto.
"""

import json
import socket
import struct
import threading
import time

# Tipos de pacote MQTT (seção 2.2.1 da especificação)
CONNECT = 1
CONNACK = 2
PUBLISH = 3
SUBSCRIBE = 8
SUBACK = 9
PINGREQ = 12
PINGRESP = 13
DISCONNECT = 14


def _codificar_string(texto: str) -> bytes:
    dados = texto.encode("utf-8")
    return struct.pack(">H", len(dados)) + dados


def _decodificar_string(buf: bytes, pos: int):
    (tamanho,) = struct.unpack(">H", buf[pos:pos + 2])
    pos += 2
    texto = buf[pos:pos + tamanho].decode("utf-8")
    return texto, pos + tamanho


def _codificar_remaining_length(tamanho: int) -> bytes:
    saida = bytearray()
    while True:
        byte = tamanho % 128
        tamanho //= 128
        if tamanho > 0:
            byte |= 0x80
        saida.append(byte)
        if tamanho == 0:
            break
    return bytes(saida)


def _ler_exato(sock: socket.socket, n: int) -> bytes:
    dados = b""
    while len(dados) < n:
        pedaco = sock.recv(n - len(dados))
        if not pedaco:
            raise ConnectionError("Conexão MQTT encerrada pelo peer")
        dados += pedaco
    return dados


def _ler_remaining_length(sock: socket.socket) -> int:
    multiplicador = 1
    valor = 0
    while True:
        byte = _ler_exato(sock, 1)[0]
        valor += (byte & 0x7F) * multiplicador
        if (byte & 0x80) == 0:
            break
        multiplicador *= 128
    return valor


def ler_pacote(sock: socket.socket):
    """Lê um pacote MQTT completo do socket. Retorna (tipo, flags, payload_bytes)."""
    primeiro_byte = _ler_exato(sock, 1)[0]
    tipo = primeiro_byte >> 4
    flags = primeiro_byte & 0x0F
    tamanho_restante = _ler_remaining_length(sock)
    payload = _ler_exato(sock, tamanho_restante) if tamanho_restante else b""
    return tipo, flags, payload


def _montar_pacote(tipo: int, flags: int, payload: bytes) -> bytes:
    cabecalho = bytes([(tipo << 4) | flags]) + _codificar_remaining_length(len(payload))
    return cabecalho + payload


def montar_connect(client_id: str, keep_alive: int = 60) -> bytes:
    # Connect flags 0x02 = Clean Session ligado, sem usuário/senha/will
    var_header = _codificar_string("MQTT") + bytes([4, 0x02]) + struct.pack(">H", keep_alive)
    payload = _codificar_string(client_id)
    return _montar_pacote(CONNECT, 0, var_header + payload)


def montar_connack(aceito: bool = True) -> bytes:
    codigo_retorno = 0x00 if aceito else 0x02  # 0x02 = identifier rejected
    return _montar_pacote(CONNACK, 0, bytes([0x00, codigo_retorno]))


def montar_publish(topico: str, payload_dict: dict) -> bytes:
    corpo = _codificar_string(topico) + json.dumps(payload_dict, ensure_ascii=False).encode("utf-8")
    return _montar_pacote(PUBLISH, 0, corpo)  # QoS 0: sem packet identifier


def desmontar_publish(payload: bytes):
    topico, pos = _decodificar_string(payload, 0)
    dados = json.loads(payload[pos:].decode("utf-8"))
    return topico, dados


def montar_subscribe(packet_id: int, topico: str) -> bytes:
    corpo = struct.pack(">H", packet_id) + _codificar_string(topico) + bytes([0x00])
    return _montar_pacote(SUBSCRIBE, 0b0010, corpo)  # flags reservadas = 0010 pela spec


def montar_suback(packet_id: int) -> bytes:
    return _montar_pacote(SUBACK, 0, struct.pack(">H", packet_id) + bytes([0x00]))


def montar_pingresp() -> bytes:
    return _montar_pacote(PINGRESP, 0, b"")


def montar_disconnect() -> bytes:
    return _montar_pacote(DISCONNECT, 0, b"")


def topico_corresponde(filtro: str, topico: str) -> bool:
    """Casamento de tópico com suporte aos wildcards '+' (nível único) e '#' (multi-nível)."""
    f_partes = filtro.split("/")
    t_partes = topico.split("/")
    for i, f in enumerate(f_partes):
        if f == "#":
            return True
        if i >= len(t_partes):
            return False
        if f != "+" and f != t_partes[i]:
            return False
    return len(f_partes) == len(t_partes)


class MQTTBroker:
    """Broker MQTT mínimo: aceita conexões TCP, processa CONNECT/SUBSCRIBE/PUBLISH
    e encaminha mensagens publicadas para todos os assinantes do tópico."""

    def __init__(self, host: str = "127.0.0.1", port: int = 18830):
        self.host = host
        self.port = port
        self._socket_servidor = None
        self._assinaturas: dict[str, set] = {}
        self._lock = threading.Lock()

    def iniciar(self) -> threading.Thread:
        self._socket_servidor = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._socket_servidor.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._socket_servidor.bind((self.host, self.port))
        self._socket_servidor.listen()
        thread = threading.Thread(target=self._aceitar_conexoes, daemon=True)
        thread.start()
        return thread

    def _aceitar_conexoes(self):
        while True:
            try:
                conn, _ = self._socket_servidor.accept()
            except OSError:
                return
            threading.Thread(target=self._lidar_cliente, args=(conn,), daemon=True).start()

    def _lidar_cliente(self, conn: socket.socket):
        try:
            tipo, _, _ = ler_pacote(conn)
            if tipo != CONNECT:
                conn.close()
                return
            conn.sendall(montar_connack(True))

            while True:
                tipo, _, payload = ler_pacote(conn)
                if tipo == SUBSCRIBE:
                    (packet_id,) = struct.unpack(">H", payload[:2])
                    filtro, _ = _decodificar_string(payload, 2)
                    with self._lock:
                        self._assinaturas.setdefault(filtro, set()).add(conn)
                    conn.sendall(montar_suback(packet_id))
                elif tipo == PUBLISH:
                    topico, dados = desmontar_publish(payload)
                    self._encaminhar(topico, dados)
                elif tipo == PINGREQ:
                    conn.sendall(montar_pingresp())
                elif tipo == DISCONNECT:
                    break
        except (ConnectionError, OSError):
            pass
        finally:
            with self._lock:
                for assinantes in self._assinaturas.values():
                    assinantes.discard(conn)
            conn.close()

    def _encaminhar(self, topico: str, dados: dict):
        pacote = montar_publish(topico, dados)
        with self._lock:
            destinos = [
                conn
                for filtro, assinantes in self._assinaturas.items()
                if topico_corresponde(filtro, topico)
                for conn in assinantes
            ]
        for conn in destinos:
            try:
                conn.sendall(pacote)
            except OSError:
                pass


class MQTTClient:
    """Cliente MQTT mínimo: conecta via TCP, publica e assina tópicos com callbacks."""

    def __init__(self, client_id: str, host: str = "127.0.0.1", port: int = 18830):
        self.client_id = client_id
        self.host = host
        self.port = port
        self._sock: socket.socket | None = None
        self._callbacks: dict[str, object] = {}
        self._packet_id = 0
        self._lock = threading.Lock()

    def conectar(self, tentativas: int = 20, espera: float = 0.25):
        ultimo_erro = None
        for _ in range(tentativas):
            try:
                self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self._sock.connect((self.host, self.port))
                break
            except (ConnectionRefusedError, OSError) as e:
                ultimo_erro = e
                time.sleep(espera)
        else:
            raise ConnectionError(f"Não foi possível conectar ao broker MQTT: {ultimo_erro}")

        self._sock.sendall(montar_connect(self.client_id))
        tipo, _, payload = ler_pacote(self._sock)
        if tipo != CONNACK or payload[1] != 0x00:
            raise ConnectionError("Broker MQTT recusou a conexão")
        threading.Thread(target=self._loop_leitura, daemon=True).start()

    def publicar(self, topico: str, payload_dict: dict):
        self._sock.sendall(montar_publish(topico, payload_dict))

    def assinar(self, filtro: str, callback):
        with self._lock:
            self._packet_id += 1
            pid = self._packet_id
            self._callbacks[filtro] = callback
        self._sock.sendall(montar_subscribe(pid, filtro))

    def desconectar(self):
        try:
            self._sock.sendall(montar_disconnect())
        except OSError:
            pass
        finally:
            self._sock.close()

    def _loop_leitura(self):
        while True:
            try:
                tipo, _, payload = ler_pacote(self._sock)
            except (ConnectionError, OSError):
                return
            if tipo == PUBLISH:
                topico, dados = desmontar_publish(payload)
                with self._lock:
                    callbacks = [
                        cb for filtro, cb in self._callbacks.items()
                        if topico_corresponde(filtro, topico)
                    ]
                for cb in callbacks:
                    cb(topico, dados)
            elif tipo == DISCONNECT:
                return

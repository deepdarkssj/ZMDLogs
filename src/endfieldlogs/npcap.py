from __future__ import annotations

import ctypes
import logging
import socket
import threading
from ctypes import POINTER
from dataclasses import dataclass
from typing import Callable

import dpkt

from .models import CapturedPacket, Endpoint, FlowKey

LOGGER = logging.getLogger(__name__)
PCAP_ERRBUF_SIZE = 256
PCAP_IF_LOOPBACK = 0x00000001
DEFAULT_BPF_FILTER = "tcp port 30000"
DEFAULT_SNAPLEN = 65535
DEFAULT_PROMISC = 0
DEFAULT_TIMEOUT_MS = 100
DEFAULT_BUFFER_SIZE = 8 * 1024 * 1024


def has_npcap() -> bool:
    try:
        ctypes.WinDLL("wpcap.dll")
    except OSError:
        return False
    return True


class timeval(ctypes.Structure):
    _fields_ = [("tv_sec", ctypes.c_long), ("tv_usec", ctypes.c_long)]


class pcap_pkthdr(ctypes.Structure):
    _fields_ = [("ts", timeval), ("caplen", ctypes.c_uint32), ("len", ctypes.c_uint32)]


class sockaddr(ctypes.Structure):
    _fields_ = [("sa_family", ctypes.c_ushort), ("sa_data", ctypes.c_ubyte * 14)]


class sockaddr_in(ctypes.Structure):
    _fields_ = [
        ("sin_family", ctypes.c_short),
        ("sin_port", ctypes.c_ushort),
        ("sin_addr", ctypes.c_ubyte * 4),
        ("sin_zero", ctypes.c_ubyte * 8),
    ]


class pcap_addr_t(ctypes.Structure):
    pass


pcap_addr_t._fields_ = [
    ("next", POINTER(pcap_addr_t)),
    ("addr", POINTER(sockaddr)),
    ("netmask", POINTER(sockaddr)),
    ("broadaddr", POINTER(sockaddr)),
    ("dstaddr", POINTER(sockaddr)),
]


class pcap_if_t(ctypes.Structure):
    pass


pcap_if_t._fields_ = [
    ("next", POINTER(pcap_if_t)),
    ("name", ctypes.c_char_p),
    ("description", ctypes.c_char_p),
    ("addresses", POINTER(pcap_addr_t)),
    ("flags", ctypes.c_uint32),
]


class bpf_program(ctypes.Structure):
    _fields_ = [("bf_len", ctypes.c_uint32), ("bf_insns", ctypes.c_void_p)]


class pcap_stat(ctypes.Structure):
    _fields_ = [("ps_recv", ctypes.c_uint), ("ps_drop", ctypes.c_uint), ("ps_ifdrop", ctypes.c_uint)]


@dataclass(slots=True)
class DeviceInfo:
    name: str
    description: str | None
    ipv4_addrs: list[str]
    flags: int


def build_flow_bpf(flow: FlowKey) -> str:
    client = flow.client
    server = flow.server
    return (
        "tcp and ("
        f"(src host {client.ip} and src port {client.port} and dst host {server.ip} and dst port {server.port}) or "
        f"(src host {server.ip} and src port {server.port} and dst host {client.ip} and dst port {client.port})"
        ")"
    )


def _device_preference_score(device: DeviceInfo, observed_device_names: set[str]) -> tuple[int, int, str]:
    description = (device.description or "").lower()
    score = 0
    if device.name in observed_device_names:
        score += 100
    if "virtual" in description or "vmware" in description or "hyper-v" in description:
        score -= 20
    if "ethernet" in description or "wi-fi" in description or "wireless" in description:
        score += 5
    return (score, len(device.ipv4_addrs), device.name)


class Wpcap:
    def __init__(self) -> None:
        self._dll = ctypes.WinDLL("wpcap.dll")
        self._dll.pcap_findalldevs.argtypes = [POINTER(POINTER(pcap_if_t)), ctypes.c_char_p]
        self._dll.pcap_findalldevs.restype = ctypes.c_int
        self._dll.pcap_freealldevs.argtypes = [POINTER(pcap_if_t)]
        self._dll.pcap_create.argtypes = [ctypes.c_char_p, ctypes.c_char_p]
        self._dll.pcap_create.restype = ctypes.c_void_p
        self._dll.pcap_set_snaplen.argtypes = [ctypes.c_void_p, ctypes.c_int]
        self._dll.pcap_set_snaplen.restype = ctypes.c_int
        self._dll.pcap_set_promisc.argtypes = [ctypes.c_void_p, ctypes.c_int]
        self._dll.pcap_set_promisc.restype = ctypes.c_int
        self._dll.pcap_set_timeout.argtypes = [ctypes.c_void_p, ctypes.c_int]
        self._dll.pcap_set_timeout.restype = ctypes.c_int
        self._dll.pcap_set_buffer_size.argtypes = [ctypes.c_void_p, ctypes.c_int]
        self._dll.pcap_set_buffer_size.restype = ctypes.c_int
        self._dll.pcap_activate.argtypes = [ctypes.c_void_p]
        self._dll.pcap_activate.restype = ctypes.c_int
        self._dll.pcap_open_live.argtypes = [
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_char_p,
        ]
        self._dll.pcap_open_live.restype = ctypes.c_void_p
        self._dll.pcap_next_ex.argtypes = [
            ctypes.c_void_p,
            POINTER(POINTER(pcap_pkthdr)),
            POINTER(POINTER(ctypes.c_ubyte)),
        ]
        self._dll.pcap_next_ex.restype = ctypes.c_int
        self._dll.pcap_close.argtypes = [ctypes.c_void_p]
        self._dll.pcap_compile.argtypes = [
            ctypes.c_void_p,
            POINTER(bpf_program),
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_uint32,
        ]
        self._dll.pcap_compile.restype = ctypes.c_int
        self._dll.pcap_setfilter.argtypes = [ctypes.c_void_p, POINTER(bpf_program)]
        self._dll.pcap_setfilter.restype = ctypes.c_int
        self._dll.pcap_freecode.argtypes = [POINTER(bpf_program)]
        self._dll.pcap_stats.argtypes = [ctypes.c_void_p, POINTER(pcap_stat)]
        self._dll.pcap_stats.restype = ctypes.c_int
        self._dll.pcap_geterr.argtypes = [ctypes.c_void_p]
        self._dll.pcap_geterr.restype = ctypes.c_char_p

    def list_devices(self) -> list[DeviceInfo]:
        alldevs = POINTER(pcap_if_t)()
        errbuf = ctypes.create_string_buffer(PCAP_ERRBUF_SIZE)
        result = self._dll.pcap_findalldevs(ctypes.byref(alldevs), errbuf)
        if result != 0:
            raise RuntimeError(errbuf.value.decode("utf-8", errors="replace"))

        devices: list[DeviceInfo] = []
        try:
            current = alldevs
            while current:
                raw = current.contents
                ipv4_addrs: list[str] = []
                addr_node = raw.addresses
                while addr_node:
                    addr = addr_node.contents.addr
                    if addr and addr.contents.sa_family == socket.AF_INET:
                        ipv4 = ctypes.cast(addr, POINTER(sockaddr_in)).contents
                        ipv4_addrs.append(socket.inet_ntoa(bytes(ipv4.sin_addr)))
                    addr_node = addr_node.contents.next
                devices.append(
                    DeviceInfo(
                        name=raw.name.decode("utf-8", errors="replace"),
                        description=raw.description.decode("utf-8", errors="replace") if raw.description else None,
                        ipv4_addrs=ipv4_addrs,
                        flags=int(raw.flags),
                    )
                )
                current = raw.next
        finally:
            self._dll.pcap_freealldevs(alldevs)
        return devices

    def open_live(self, device_name: str, bpf_filter: str) -> ctypes.c_void_p:
        try:
            return self._open_activated(device_name, bpf_filter)
        except Exception as exc:
            LOGGER.warning("pcap_create/activate failed for %s, falling back to open_live: %s", device_name, exc)
            return self._open_live_fallback(device_name, bpf_filter)

    def _open_activated(self, device_name: str, bpf_filter: str) -> ctypes.c_void_p:
        errbuf = ctypes.create_string_buffer(PCAP_ERRBUF_SIZE)
        handle = self._dll.pcap_create(device_name.encode("utf-8"), errbuf)
        if not handle:
            raise RuntimeError(errbuf.value.decode("utf-8", errors="replace"))
        try:
            self._check_status(handle, self._dll.pcap_set_snaplen(handle, DEFAULT_SNAPLEN), "pcap_set_snaplen")
            self._check_status(handle, self._dll.pcap_set_promisc(handle, DEFAULT_PROMISC), "pcap_set_promisc")
            self._check_status(handle, self._dll.pcap_set_timeout(handle, DEFAULT_TIMEOUT_MS), "pcap_set_timeout")
            self._check_status(
                handle,
                self._dll.pcap_set_buffer_size(handle, DEFAULT_BUFFER_SIZE),
                "pcap_set_buffer_size",
            )
            self._check_status(handle, self._dll.pcap_activate(handle), "pcap_activate")
            self._apply_bpf_filter(handle, bpf_filter)
            LOGGER.info(
                "opened %s via pcap_create/activate buffer=%d timeout_ms=%d",
                device_name,
                DEFAULT_BUFFER_SIZE,
                DEFAULT_TIMEOUT_MS,
            )
            return handle
        except Exception:
            self._dll.pcap_close(handle)
            raise

    def _open_live_fallback(self, device_name: str, bpf_filter: str) -> ctypes.c_void_p:
        errbuf = ctypes.create_string_buffer(PCAP_ERRBUF_SIZE)
        handle = self._dll.pcap_open_live(
            device_name.encode("utf-8"),
            DEFAULT_SNAPLEN,
            DEFAULT_PROMISC,
            DEFAULT_TIMEOUT_MS,
            errbuf,
        )
        if not handle:
            raise RuntimeError(errbuf.value.decode("utf-8", errors="replace"))
        try:
            self._apply_bpf_filter(handle, bpf_filter)
            LOGGER.info("opened %s via pcap_open_live timeout_ms=%d", device_name, DEFAULT_TIMEOUT_MS)
            return handle
        except Exception:
            self._dll.pcap_close(handle)
            raise

    def _apply_bpf_filter(self, handle: ctypes.c_void_p, bpf_filter: str) -> None:
        program = bpf_program()
        result = self._dll.pcap_compile(handle, ctypes.byref(program), bpf_filter.encode("utf-8"), 1, 0xFFFFFFFF)
        if result != 0:
            message = self._dll.pcap_geterr(handle).decode("utf-8", errors="replace")
            raise RuntimeError(message)
        try:
            result = self._dll.pcap_setfilter(handle, ctypes.byref(program))
            if result != 0:
                message = self._dll.pcap_geterr(handle).decode("utf-8", errors="replace")
                raise RuntimeError(message)
        finally:
            self._dll.pcap_freecode(ctypes.byref(program))

    def _check_status(self, handle: ctypes.c_void_p, result: int, operation: str) -> None:
        if result == 0:
            return
        message = self._dll.pcap_geterr(handle)
        decoded = message.decode("utf-8", errors="replace") if message else f"{operation} failed with code {result}"
        raise RuntimeError(decoded)

    def close(self, handle: ctypes.c_void_p) -> None:
        self._dll.pcap_close(handle)

    def stats(self, handle: ctypes.c_void_p) -> pcap_stat | None:
        value = pcap_stat()
        if self._dll.pcap_stats(handle, ctypes.byref(value)) != 0:
            return None
        return value

    def next_packet(self, handle: ctypes.c_void_p) -> tuple[int, bytes] | None:
        header_ptr = POINTER(pcap_pkthdr)()
        data_ptr = POINTER(ctypes.c_ubyte)()
        result = self._dll.pcap_next_ex(handle, ctypes.byref(header_ptr), ctypes.byref(data_ptr))
        if result <= 0:
            return None
        header = header_ptr.contents
        packet_data = ctypes.string_at(data_ptr, header.caplen)
        timestamp_ms = int(header.ts.tv_sec * 1000 + header.ts.tv_usec / 1000)
        return timestamp_ms, packet_data


class CaptureHandle:
    def __init__(
        self,
        api: Wpcap,
        device: DeviceInfo,
        bpf_filter: str,
        on_packet: Callable[[CapturedPacket], None],
    ) -> None:
        self._api = api
        self._device = device
        self._handle = api.open_live(device.name, bpf_filter)
        self._on_packet = on_packet
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name=f"pcap:{device.name}", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=2)
        self._api.close(self._handle)

    def stats(self) -> pcap_stat | None:
        return self._api.stats(self._handle)

    @property
    def device(self) -> DeviceInfo:
        return self._device

    def _run(self) -> None:
        while not self._stop.is_set():
            packet = self._api.next_packet(self._handle)
            if packet is None:
                continue
            timestamp_ms, raw = packet
            try:
                eth = dpkt.ethernet.Ethernet(raw)
                ip = eth.data
                if not isinstance(ip, dpkt.ip.IP):
                    continue
                tcp = ip.data
                if not isinstance(tcp, dpkt.tcp.TCP) or not tcp.data:
                    continue
                captured = CapturedPacket(
                    timestamp_ms=timestamp_ms,
                    src=Endpoint(socket.inet_ntoa(ip.src), int(tcp.sport)),
                    dst=Endpoint(socket.inet_ntoa(ip.dst), int(tcp.dport)),
                    seq=int(tcp.seq),
                    payload=bytes(tcp.data),
                    device_name=self._device.name,
                )
            except (dpkt.UnpackError, ValueError):
                continue
            self._on_packet(captured)


class CaptureManager:
    def __init__(self, api: Wpcap, devices: list[DeviceInfo], on_packet: Callable[[CapturedPacket], None]) -> None:
        self._api = api
        self._default_devices = list(devices)
        self._on_packet = on_packet
        self._lock = threading.Lock()
        self._locked_flow: FlowKey | None = None
        self._locked_device_name: str | None = None
        self._handles = self._build_handles(devices, DEFAULT_BPF_FILTER)

    @classmethod
    def create(cls, requested_device: str, on_packet: Callable[[CapturedPacket], None]) -> "CaptureManager":
        api = Wpcap()
        devices = api.list_devices()
        if requested_device == "auto":
            selected = [
                device
                for device in devices
                if not (device.flags & PCAP_IF_LOOPBACK) and device.ipv4_addrs
            ]
        else:
            pattern = requested_device.lower()
            selected = [
                device
                for device in devices
                if pattern in device.name.lower()
                or (device.description and pattern in device.description.lower())
            ]
        if not selected:
            raise RuntimeError(f"no Npcap devices matched {requested_device!r}")
        LOGGER.info("opening %d Npcap device(s)", len(selected))
        return cls(api, selected, on_packet)

    def start(self) -> None:
        for handle in self._snapshot_handles():
            handle.start()

    def stop(self) -> None:
        with self._lock:
            handles = self._handles
            self._handles = []
            self._locked_flow = None
            self._locked_device_name = None
        for handle in handles:
            handle.stop()

    def lock_to_flow(self, flow: FlowKey, observed_device_names: set[str]) -> None:
        with self._lock:
            if self._locked_flow == flow and self._locked_device_name is not None:
                return
            device = self._select_device(flow, observed_device_names)
            if device is None:
                LOGGER.warning(
                    "could not determine capture device for flow %s:%d -> %s:%d; keeping broad capture",
                    flow.client.ip,
                    flow.client.port,
                    flow.server.ip,
                    flow.server.port,
                )
                return
            bpf_filter = build_flow_bpf(flow)
            new_handles = self._build_handles([device], bpf_filter)
            old_handles = self._handles
            self._handles = new_handles
            self._locked_flow = flow
            self._locked_device_name = device.name
        LOGGER.info("locking capture to device %s with exact flow BPF", device.name)
        for handle in new_handles:
            handle.start()
        for handle in old_handles:
            handle.stop()

    def restore_default_filters(self) -> None:
        with self._lock:
            if self._locked_flow is None and len(self._handles) == len(self._default_devices):
                return
            new_handles = self._build_handles(self._default_devices, DEFAULT_BPF_FILTER)
            old_handles = self._handles
            self._handles = new_handles
            self._locked_flow = None
            self._locked_device_name = None
        LOGGER.info("restoring discovery capture across %d device(s)", len(new_handles))
        for handle in new_handles:
            handle.start()
        for handle in old_handles:
            handle.stop()

    def stats_snapshot(self) -> dict[str, int]:
        recv = 0
        drop = 0
        ifdrop = 0
        for handle in self._snapshot_handles():
            stats = handle.stats()
            if stats is None:
                continue
            recv += int(stats.ps_recv)
            drop += int(stats.ps_drop)
            ifdrop += int(stats.ps_ifdrop)
        return {"ps_recv": recv, "ps_drop": drop, "ps_ifdrop": ifdrop}

    def _build_handles(self, devices: list[DeviceInfo], bpf_filter: str) -> list[CaptureHandle]:
        return [CaptureHandle(self._api, device, bpf_filter, self._on_packet) for device in devices]

    def _snapshot_handles(self) -> list[CaptureHandle]:
        with self._lock:
            return list(self._handles)

    def _select_device(self, flow: FlowKey, observed_device_names: set[str]) -> DeviceInfo | None:
        exact_ip_matches = [device for device in self._default_devices if flow.client.ip in device.ipv4_addrs]
        if exact_ip_matches:
            candidates = exact_ip_matches
        elif observed_device_names:
            candidates = [device for device in self._default_devices if device.name in observed_device_names]
        else:
            candidates = list(self._default_devices)
        if not candidates:
            return None
        candidates.sort(key=lambda device: _device_preference_score(device, observed_device_names), reverse=True)
        return candidates[0]

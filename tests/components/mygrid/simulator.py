"""Small independent Modbus TCP peer, based on the manual's wire contract."""

import asyncio
import struct
from contextlib import suppress


class BatterySimulator:
    """Serve raw MBAP frames without using client decoding or pymodbus."""

    def __init__(self, registers: list[int]) -> None:
        self.registers = list(registers)
        self.requests: list[tuple[int, int, int]] = []
        self.writes: list[tuple[int, int]] = []
        self.total_connections = 0
        self.connections = 0
        self.maximum_connections = 0
        self.rejects = 0
        self.drop_write_response = False
        self.drop_read_response = False
        self.next_exception: int | None = None
        self.clamp_charge_to: int | None = None
        self.writers: set[asyncio.StreamWriter] = set()
        self.tasks: set[asyncio.Task] = set()
        self.server: asyncio.Server | None = None
        self.port = 0

    async def __aenter__(self):
        self.server = await asyncio.start_server(self._connected, "127.0.0.1", 0)
        self.port = self.server.sockets[0].getsockname()[1]
        return self

    async def __aexit__(self, *args):
        self.server.close()
        await self.server.wait_closed()
        for writer in list(self.writers):
            writer.close()
        if self.tasks:
            await asyncio.gather(*self.tasks)

    def _connected(self, reader, writer):
        task = asyncio.create_task(self._serve(reader, writer))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    async def _serve(self, reader, writer):
        self.total_connections += 1
        self.writers.add(writer)
        if self.connections:
            self.rejects += 1
            writer.close()
            await writer.wait_closed()
            self.writers.discard(writer)
            return
        self.connections += 1
        self.maximum_connections = max(self.maximum_connections, self.connections)
        try:
            while True:
                header = await reader.readexactly(7)
                transaction, protocol, length, unit = struct.unpack(">HHHB", header)
                assert protocol == 0
                body = await reader.readexactly(length - 1)
                function, address, value = struct.unpack(">BHH", body)
                self.requests.append((function, address, value))
                if unit != 1:
                    response = bytes([function | 128, 10])
                elif self.next_exception is not None:
                    response = bytes([function | 128, self.next_exception])
                    self.next_exception = None
                elif function == 3:
                    if self.drop_read_response:
                        return
                    if address + value > 18 or not value:
                        response = bytes([131, 2])
                    else:
                        words = self.registers[address : address + value]
                        response = struct.pack(">BB", 3, len(words) * 2) + struct.pack(
                            f">{len(words)}H", *words
                        )
                elif function == 6:
                    if address not in (2, 9):
                        response = bytes([134, 2])
                    elif address == 9 and value != 1:
                        response = bytes([134, 3])
                    else:
                        self.writes.append((address, value))
                        if address == 2:
                            signed = struct.unpack(">h", struct.pack(">H", value))[0]
                            limit = (
                                self.clamp_charge_to
                                if self.clamp_charge_to is not None
                                else self.registers[3]
                            )
                            accepted = max(-self.registers[4], min(signed, limit))
                            self.registers[2] = accepted & 65535
                        if self.drop_write_response:
                            return
                        response = body
                else:
                    response = bytes([function | 128, 1])
                writer.write(
                    struct.pack(">HHHB", transaction, 0, len(response) + 1, unit)
                    + response
                )
                await writer.drain()
        except asyncio.IncompleteReadError, ConnectionError:
            pass
        finally:
            self.connections -= 1
            writer.close()
            with suppress(ConnectionError):
                await writer.wait_closed()
            self.writers.discard(writer)

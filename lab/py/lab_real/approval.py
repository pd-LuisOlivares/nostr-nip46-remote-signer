"""Aprobacion humana por solicitud. Denegacion por defecto.

TtyApprover pregunta en la terminal interactiva. ScriptedApprover solo existe para el ENSAYO local y se
rechaza si el relay no es el del laboratorio (guarda anti-automatizacion contra relays reales).
"""
import asyncio
import collections
import time

LAB_HOSTS = frozenset({"relay", "relay-lab"})
YES = ("s", "si", "sí", "y", "yes")


class ApprovalConfigError(Exception):
    pass


class TtyApprover:
    async def ask(self, kind: str, text: str) -> bool:
        print(text, flush=True)
        loop = asyncio.get_running_loop()
        answer = await loop.run_in_executor(None, lambda: input("> "))
        return answer.strip().lower() in YES


class ScriptedApprover:
    """script: 'connect=y,sign=y,sign=n,sign=timeout'. Lo no listado se deniega."""

    def __init__(self, script: str):
        self.answers: dict[str, collections.deque] = collections.defaultdict(collections.deque)
        for part in filter(None, (p.strip() for p in script.split(","))):
            kind, _, ans = part.partition("=")
            self.answers[kind].append(ans.strip().lower())

    async def ask(self, kind: str, text: str) -> bool:
        print(text, flush=True)
        ans = self.answers[kind].popleft() if self.answers[kind] else "n"
        if ans == "timeout":
            await asyncio.sleep(3600)
        return ans in YES


def make_approver(mode: str, relay_host: str, script: str = ""):
    if mode == "tty":
        return TtyApprover()
    if mode == "scripted":
        if relay_host not in LAB_HOSTS:
            raise ApprovalConfigError("la aprobacion automatica solo se permite con el relay del laboratorio")
        return ScriptedApprover(script)
    raise ApprovalConfigError(f"modo de aprobacion desconocido: {mode}")


async def decide(approver, kind: str, text: str, timeout_s: float) -> tuple[bool, str, int]:
    """(aprobado, motivo, latencia_ms). Motivos: humano, timeout, error."""
    t0 = time.monotonic()
    try:
        approved = await asyncio.wait_for(approver.ask(kind, text), timeout_s)
        reason = "humano"
    except asyncio.TimeoutError:
        approved, reason = False, "timeout"
    except (EOFError, OSError):
        approved, reason = False, "error"
    return approved, reason, int((time.monotonic() - t0) * 1000)

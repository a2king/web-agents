from __future__ import annotations

import os
import shutil
import subprocess
from abc import ABC, abstractmethod
from pathlib import Path


class Runtime(ABC):
    @abstractmethod
    def ensure_workspace(self, tenant_id: int) -> Path:
        raise NotImplementedError

    @abstractmethod
    def session_dir(self, tenant_id: int, session_id: int) -> Path:
        raise NotImplementedError

    @abstractmethod
    def shared_dir(self, tenant_id: int) -> Path:
        raise NotImplementedError

    @abstractmethod
    def skills_dir(self, tenant_id: int) -> Path:
        raise NotImplementedError

    @abstractmethod
    def run_command(
        self,
        tenant_id: int,
        command: str,
        cwd: Path,
        timeout: int = 120,
        env: dict | None = None,
    ) -> tuple[int, str, str]:
        raise NotImplementedError

    @abstractmethod
    def destroy_workspace(self, tenant_id: int) -> None:
        raise NotImplementedError


class LocalRuntime(Runtime):
    """单机本地隔离：每个租户独立目录。后期可替换为 Docker / 多机 SSH。"""

    def __init__(self, data_dir: str):
        self.root = Path(data_dir)

    def tenant_root(self, tenant_id: int) -> Path:
        return self.root / "tenants" / str(tenant_id)

    def ensure_workspace(self, tenant_id: int) -> Path:
        root = self.tenant_root(tenant_id)
        (root / "sessions").mkdir(parents=True, exist_ok=True)
        (root / "shared").mkdir(parents=True, exist_ok=True)
        (root / "skills").mkdir(parents=True, exist_ok=True)
        return root

    def session_dir(self, tenant_id: int, session_id: int) -> Path:
        path = self.ensure_workspace(tenant_id) / "sessions" / str(session_id)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def shared_dir(self, tenant_id: int) -> Path:
        path = self.ensure_workspace(tenant_id) / "shared"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def skills_dir(self, tenant_id: int) -> Path:
        path = self.ensure_workspace(tenant_id) / "skills"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def run_command(
        self,
        tenant_id: int,
        command: str,
        cwd: Path,
        timeout: int = 120,
        env: dict | None = None,
    ) -> tuple[int, str, str]:
        self.ensure_workspace(tenant_id)
        merged = os.environ.copy()
        if env:
            merged.update(env)
        try:
            proc = subprocess.run(
                command,
                shell=True,
                cwd=str(cwd),
                capture_output=True,
                text=True,
                timeout=timeout,
                env=merged,
            )
            return proc.returncode, proc.stdout, proc.stderr
        except subprocess.TimeoutExpired as exc:
            return 124, exc.stdout or "", (exc.stderr or "") + "\n命令超时"

    def destroy_workspace(self, tenant_id: int) -> None:
        root = self.tenant_root(tenant_id)
        if root.exists():
            shutil.rmtree(root)


class DockerRuntime(LocalRuntime):
    """预留：按租户 CPU/内存拉起容器。第一期回退到本地目录隔离。"""

    def __init__(self, data_dir: str):
        super().__init__(data_dir)
        self.available = shutil.which("docker") is not None

    def run_command(
        self,
        tenant_id: int,
        command: str,
        cwd: Path,
        timeout: int = 120,
        env: dict | None = None,
    ) -> tuple[int, str, str]:
        if not self.available:
            return super().run_command(tenant_id, command, cwd, timeout, env)
        root = self.ensure_workspace(tenant_id)
        rel = cwd.resolve().relative_to(root.resolve())
        docker_cwd = f"/workspace/{rel.as_posix()}"
        cpu = env.pop("TENANT_CPU", "1") if env else "1"
        memory = env.pop("TENANT_MEMORY", "1g") if env else "1g"
        docker_cmd = [
            "docker",
            "run",
            "--rm",
            f"--cpus={cpu}",
            f"--memory={memory}",
            "-v",
            f"{root}:/workspace",
            "-w",
            docker_cwd,
            "python:3.12-slim",
            "bash",
            "-lc",
            command,
        ]
        try:
            proc = subprocess.run(docker_cmd, capture_output=True, text=True, timeout=timeout)
            return proc.returncode, proc.stdout, proc.stderr
        except FileNotFoundError:
            return super().run_command(tenant_id, command, cwd, timeout, env)
        except subprocess.TimeoutExpired as exc:
            return 124, exc.stdout or "", (exc.stderr or "") + "\n命令超时"


class RemoteSshRuntime(LocalRuntime):
    """预留多机免密调度：根据节点选择 SSH 执行。"""

    def __init__(self, data_dir: str, nodes: list[dict] | None = None):
        super().__init__(data_dir)
        self.nodes = nodes or []

    def pick_node(self) -> dict | None:
        return self.nodes[0] if self.nodes else None


def create_runtime(app) -> Runtime:
    backend = app.config.get("RUNTIME_BACKEND", "local")
    data_dir = app.config["DATA_DIR"]
    if backend == "docker":
        return DockerRuntime(data_dir)
    if backend == "ssh":
        return RemoteSshRuntime(data_dir)
    return LocalRuntime(data_dir)

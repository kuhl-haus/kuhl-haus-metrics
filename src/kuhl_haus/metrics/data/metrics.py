from __future__ import annotations

import json
import time
import traceback
from dataclasses import dataclass, field
from typing import Any, List, Dict, Optional
from logging import Logger
from kuhl_haus.metrics.clients.carbon_poster import CarbonPoster


@dataclass()
class Metrics:
    mnemonic: str
    namespace: str
    hostname: Optional[str] = ""
    timestamp: Optional[int] = -1
    meta: Optional[Dict[str, Any]] = field(default_factory=dict)
    attributes: Optional[Dict[str, Any]] = field(default_factory=dict)
    counters:  Optional[Dict[str, int]] = field(default_factory=dict)

    def __post_init__(self):
        if self.timestamp == -1:
            self.timestamp = time.time_ns() // 1_000_000_000

    def declare_counters(self, counters: List[str]):
        while counters:
            counter = counters.pop()
            self.counters[counter] = 0

    def set_counter(self, counter: str, increment: int):
        if counter in self.counters:
            self.counters[counter] += increment
        else:
            self.counters[counter] = increment

    @property
    def json(self) -> str:
        serialized_result = json.dumps(
            {
                "mnemonic": self.mnemonic,
                "namespace": self.namespace,
                "timestamp": self.timestamp,
                "meta": self.meta,
                "attributes": self.attributes,
                "counters": self.counters,
            }
        )
        return serialized_result

    @property
    def carbon(self) -> List[tuple]:
        metrics = []
        tags = self.__get_tags()
        tagged_path = f"{self.namespace}.mnemonic.{self.mnemonic}.%s{tags}"
        self.__add_attributes(path=tagged_path, metrics=metrics)
        self.__add_counters(path=tagged_path, metrics=metrics)

        mnemonic_path = f"{self.namespace}.mnemonic.{self.mnemonic}.%s"
        self.__add_attributes(path=mnemonic_path, metrics=metrics)
        self.__add_counters(path=mnemonic_path, metrics=metrics)
        if self.hostname:
            dotless_hostname = self.hostname.replace('.', '_')
            hostname_path = f"{self.namespace}.hostname.{dotless_hostname}.{self.mnemonic}.%s"
            self.__add_attributes(path=hostname_path, metrics=metrics)
            self.__add_counters(path=hostname_path, metrics=metrics)

        return metrics

    def __get_tags(self) -> str:
        # disk.used;datacenter=dc1;rack=a1;server=web01
        tags = ""
        for k, v in self.meta.items():
            try:
                if v:
                    tags += f";{k}={v}"
            except ValueError:
                continue
        return tags

    def __add_attributes(self, path: str, metrics: List[tuple]):
        for k, v in self.attributes.items():
            try:
                if isinstance(v, (int, float)):
                    metrics.extend([(path % k, (self.timestamp, v)),])
                elif isinstance(v, str):
                    whole, sep, _ = v.partition('.')
                    value = int(whole)
                    metrics.extend([(path % k, (self.timestamp, value)),])
            except ValueError:
                continue

    def __add_counters(self, path: str, metrics: List[tuple]):
        for k, v in self.counters.items():
            try:
                metrics.extend([(path % k, (self.timestamp, int(v))),])
            except ValueError:
                continue

    def post_metrics(self, logger: Logger, poster: CarbonPoster):
        try:
            carbon_metrics = self.carbon
            poster.post_metrics(carbon_metrics)
            logger.debug(f"Posted {len(carbon_metrics)} metrics to Graphite.")
            logger.debug(f"Metrics: {carbon_metrics}")
        except Exception as e:
            logger.error(
                f"Unhandled exception raised while posting metrics for {self.mnemonic} ({repr(e)})\r\n"
                f"{traceback.format_exc()}"
            )

    def log_metrics(self, logger: Logger):
        try:
            logger.info(self.json)
        except Exception as e:
            logger.error(
                f"Unhandled exception raised while logging for {self.mnemonic} ({repr(e)})\r\n"
                f"{traceback.format_exc()}"
            )

    @staticmethod
    def version_to_float(version_string: str) -> float:
        """
        This approach allows minor up to 99 and build is unconstrained

        Removes any pre-release or build metadata for semver compatibility

        Format: MajorMinor.Build (where minor is padded to 2 digits)

        0.0.1     ->     0.1
        0.0.100   ->   0.100
        0.1.0     ->       1
        0.1.1     ->     1.1
        0.99.1    ->    99.1
        0.100.1   ->    99.1
        1.0.0     ->     100
        1.1.0     ->     110
        1.0.1     ->   100.1
        1.1.1     ->   101.1
        """

        base_version = version_string.split('-')[0].split('+')[0]
        parts = base_version.split('.')

        major = int(parts[0])
        minor = int(parts[1]) if len(parts) > 1 else 0
        build = int(parts[2]) if len(parts) > 2 else 0

        minor = min(minor, 99)
        minor_str = f"{minor:02d}"
        build_str = f"{build:d}"

        # Combine as a float
        return float(f"{major}{minor_str}.{build_str}")

    @staticmethod
    def version_to_int(version_string: str) -> int:
        """
        This approach allows minor and build up to 99

        Removes any pre-release or build metadata for semver compatibility

        Format: MajorMinor.Build (where minor and build are padded to 2 digits)
        0.0.1    ->         1
        0.0.9    ->         9
        0.0.10   ->        10
        0.0.99   ->        99
        0.0.100  ->        99
        0.1.0    ->       100
        0.1.1    ->       101
        0.9.0    ->       900
        0.10.0   ->      1000
        0.99.0   ->      9900
        0.100.0  ->      9900
        1.0.0    ->    10,000
        """
        base_version = version_string.split('-')[0].split('+')[0]
        parts = base_version.split('.')

        major = int(parts[0])
        minor = int(parts[1]) if len(parts) > 1 else 0
        build = int(parts[2]) if len(parts) > 2 else 0

        minor = min(minor, 99)
        minor_str = f"{minor:02d}"
        build = min(build, 99)
        build_str = f"{build:02d}"

        return int(f"{major}{minor_str}{build_str}")

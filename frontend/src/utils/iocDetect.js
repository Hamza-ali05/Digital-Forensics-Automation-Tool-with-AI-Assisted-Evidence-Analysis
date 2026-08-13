/**
 * Client-side IOC detection mirroring ``dfat.forensic_engine.processing.ioc_detector``.
 */

import { ARTEFACT_CATEGORY } from "utils/constants";

export const SUSPICIOUS_PROCESSES = [
  "mimikatz",
  "psexec",
  "procdump",
  "lazagne",
  "bloodhound",
  "rubeus",
  "sharphound",
  "cobalt",
  "beacon",
];

export const SUSPICIOUS_REGISTRY_PATHS = [
  "\\Run\\",
  "\\RunOnce\\",
  "\\Services\\",
  "\\Winlogon\\Shell",
  "\\Image File Execution Options\\",
];

export const SUSPICIOUS_EXTENSIONS = [
  ".ps1",
  ".vbs",
  ".bat",
  ".cmd",
  ".hta",
  ".scr",
];

export const EXTERNAL_PORT_INDICATORS = [
  4444, 5555, 8080, 1337, 31337, 6666, 6667,
];

/** Map detector ioc_type → dashboard display type. */
export const IOC_DISPLAY_TYPE = {
  suspicious_process: "process",
  suspicious_registry: "registry",
  suspicious_extension: "file",
  deleted_suspicious_file: "file",
  suspicious_port: "network",
  external_connection: "network",
  injected_code: "injection",
};

function asInt(value) {
  if (value == null || value === "") return null;
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

function suspiciousExtension(path) {
  const text = String(path || "").toLowerCase();
  return SUSPICIOUS_EXTENSIONS.find((ext) => text.endsWith(ext)) || null;
}

function scanProcess(artefact, raw) {
  const matches = [];
  const name = String(raw.name || raw.process_name || "");
  const cmdline = String(raw.command_line || "");
  const haystacks = [name, cmdline];
  SUSPICIOUS_PROCESSES.forEach((process) => {
    const needle = process.toLowerCase();
    if (haystacks.some((text) => text && text.toLowerCase().includes(needle))) {
      matches.push({
        artefact_id: artefact.artefact_id,
        ioc_type: "suspicious_process",
        indicator: process,
        confidence: "high",
        description: `Process artefact references known suspicious tool '${process}'`,
        matched_rule: "SUSPICIOUS_PROCESSES",
      });
    }
  });
  return matches;
}

function scanRegistry(artefact, raw) {
  const matches = [];
  const keyPath = String(raw.key_path || "");
  const normalised = keyPath.replace(/\//g, "\\");
  SUSPICIOUS_REGISTRY_PATHS.forEach((pattern) => {
    if (normalised.toLowerCase().includes(pattern.toLowerCase())) {
      matches.push({
        artefact_id: artefact.artefact_id,
        ioc_type: "suspicious_registry",
        indicator: pattern,
        confidence: "medium",
        description: `Registry key path matches persistence pattern '${pattern}'`,
        matched_rule: "SUSPICIOUS_REGISTRY_PATHS",
      });
    }
  });
  return matches;
}

function scanFilesystem(artefact, raw) {
  const path = String(raw.path || raw.filename || "");
  const ext = suspiciousExtension(path);
  if (!ext) return [];
  if (raw.is_deleted === true) {
    return [
      {
        artefact_id: artefact.artefact_id,
        ioc_type: "deleted_suspicious_file",
        indicator: ext,
        confidence: "high",
        description: `Deleted file with suspicious extension '${ext}': ${path}`,
        matched_rule: "SUSPICIOUS_EXTENSIONS+DELETED",
      },
    ];
  }
  return [
    {
      artefact_id: artefact.artefact_id,
      ioc_type: "suspicious_extension",
      indicator: ext,
      confidence: "low",
      description: `File with suspicious extension '${ext}': ${path}`,
      matched_rule: "SUSPICIOUS_EXTENSIONS",
    },
  ];
}

function scanNetwork(artefact, raw) {
  const matches = [];
  ["remote_port", "local_port"].forEach((portKey) => {
    const port = asInt(raw[portKey]);
    if (port != null && EXTERNAL_PORT_INDICATORS.includes(port)) {
      matches.push({
        artefact_id: artefact.artefact_id,
        ioc_type: "suspicious_port",
        indicator: String(port),
        confidence: "high",
        description: `Network connection uses known suspicious port ${port} (${portKey})`,
        matched_rule: "EXTERNAL_PORT_INDICATORS",
      });
    }
  });
  if (raw.is_external === true) {
    const remote = String(raw.remote_address || "");
    matches.push({
      artefact_id: artefact.artefact_id,
      ioc_type: "external_connection",
      indicator: remote || "unknown",
      confidence: "medium",
      description: `Network connection to external address '${remote}'`,
      matched_rule: "EXTERNAL_IP",
    });
  }
  return matches;
}

function scanInjection(artefact, raw) {
  const indicators = raw.suspicious_indicators || [];
  let indicator;
  let confidence;
  if (Array.isArray(indicators) && indicators.length) {
    indicator = indicators.map(String).join(", ");
    confidence = "high";
  } else {
    indicator = String(raw.vad_start || "injected_region");
    confidence = "medium";
  }
  const process = raw.process_name || raw.pid || "unknown";
  return [
    {
      artefact_id: artefact.artefact_id,
      ioc_type: "injected_code",
      indicator,
      confidence,
      description: `Injected code finding in process '${process}'`,
      matched_rule: "INJECTED_CODE",
    },
  ];
}

function scanArtefact(artefact) {
  const raw =
    artefact?.raw_data && typeof artefact.raw_data === "object"
      ? artefact.raw_data
      : {};
  const category = String(artefact?.category || "").toLowerCase();

  if (category === ARTEFACT_CATEGORY.RUNNING_PROCESS) {
    return scanProcess(artefact, raw);
  }
  if (category === ARTEFACT_CATEGORY.REGISTRY_KEY) {
    return scanRegistry(artefact, raw);
  }
  if (category === ARTEFACT_CATEGORY.FILESYSTEM_METADATA) {
    return scanFilesystem(artefact, raw);
  }
  if (category === ARTEFACT_CATEGORY.NETWORK_CONNECTION) {
    return scanNetwork(artefact, raw);
  }
  if (category === ARTEFACT_CATEGORY.INJECTED_CODE) {
    return scanInjection(artefact, raw);
  }
  return [];
}

/**
 * Detect IOCs across an artefact collection.
 */
export function detectIocs(artefacts = []) {
  const matches = [];
  (artefacts || []).forEach((artefact) => {
    matches.push(...scanArtefact(artefact));
  });
  return matches;
}

export function iocDisplayType(iocType) {
  return IOC_DISPLAY_TYPE[iocType] || String(iocType || "unknown")
    .replace(/^suspicious_/, "")
    .replace(/_/g, " ");
}

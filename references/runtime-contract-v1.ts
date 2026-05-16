export type RegistrationMode = "public_builtin" | "local_override_only";

export type RuntimeMode = "openclaw_native" | "direct_cli" | "acp";

export type ContinuityMode =
  | "authoritative_resume"
  | "mapped_resume"
  | "degraded_resume"
  | "stateless_only";

export type FallbackPolicy =
  | "fail_closed"
  | "fallback_to_stateless"
  | "fallback_to_legacy_runtime"
  | "disallowed";

export type CapabilitySurface =
  | "runtime_managed"
  | "client_mediated"
  | "mixed"
  | "unknown";

export type OrchestrationSupportLevel =
  | "native"
  | "compatible_with_client_layer"
  | "partial"
  | "unsupported"
  | "unknown";

export type LaunchSurface =
  | "managed_runtime"
  | "subprocess"
  | "protocol_adapter";

export type HandleAcquisitionStrategy =
  | "protocol_native"
  | "session_id_returned"
  | "local_mapping"
  | "heuristic_discovery"
  | "none";

export type HandleScope = "session" | "conversation" | "turn_only" | "unknown";

export type FileIOSurface = "runtime_managed" | "client_mediated" | "mixed" | "unknown";

export type TerminalExecutionSurface =
  | "runtime_managed"
  | "client_mediated"
  | "unsupported"
  | "unknown";

export interface RuntimeContractV1 {
  engine_id: string;
  display_name: string;

  registration_mode: RegistrationMode;
  runtime_mode: RuntimeMode;

  continuity_mode: ContinuityMode;
  resume_requires_same_runtime_state: boolean;

  fallback_policy: FallbackPolicy;
  capability_surface: CapabilitySurface;

  orchestration_support_level: OrchestrationSupportLevel;

  launch_surface?: LaunchSurface;
  handle_acquisition_strategy?: HandleAcquisitionStrategy;
  handle_scope?: HandleScope;
  file_io_surface?: FileIOSurface;
  terminal_execution_surface?: TerminalExecutionSurface;
}

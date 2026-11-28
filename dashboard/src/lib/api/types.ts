import type { components } from "./schema";

export type Schemas = components["schemas"];
export type Memory = Schemas["MemoryRecord"];
export type MemoryDetail = Schemas["MemoryDetail"];
export type MemoryPage = Schemas["MemoryPage"];
export type DreamRun = Schemas["DreamRunRecord"];
export type DreamSchedule = Schemas["DreamSchedule"];
export type Checkpoint = Schemas["CheckpointRecord"];
export type TaskQueue = Schemas["TaskQueue"];
export type RepoBranch = Schemas["RepoBranch"];
export type ProjectProfile = Schemas["ProjectProfileOut"];
export type ProfileEntry = Schemas["ProfileEntryOut"];
export type ProfileSection = ProfileEntry["section"];
export type ConflictView = Schemas["ConflictView"];
export type Resolution = Schemas["ConflictResolution"]["resolution"];
export type Device = Schemas["DeviceRecord"];
export type CreatedDevice = Schemas["CreatedDevice"];
export type MemoryType = Memory["type"];
export type MemoryScope = Memory["scope"];

export const MEMORY_TYPES: readonly MemoryType[] = [
  "fact",
  "decision",
  "convention",
  "gotcha",
  "todo",
];
export const MEMORY_SCOPES: readonly MemoryScope[] = ["global", "repo", "branch"];

export const PROFILE_SECTIONS: readonly { key: ProfileSection; title: string }[] = [
  { key: "stack", title: "Stack" },
  { key: "conventions", title: "Conventions" },
  { key: "architecture", title: "Architecture notes" },
  { key: "decisions", title: "Key decisions" },
  { key: "open_work", title: "Open work" },
  { key: "pitfalls", title: "Known pitfalls" },
];

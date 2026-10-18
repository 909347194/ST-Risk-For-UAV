CREATE TABLE "dispatch_events" (
	"id" text PRIMARY KEY NOT NULL,
	"run_id" text NOT NULL,
	"type" text NOT NULL,
	"reason" text,
	"payload" jsonb,
	"created_at" timestamp DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "flight_logs" (
	"id" text PRIMARY KEY NOT NULL,
	"uav_id" text NOT NULL,
	"track" geometry(point),
	"start_time" timestamp,
	"end_time" timestamp,
	"total_distance" real
);
--> statement-breakpoint
CREATE TABLE "plans" (
	"id" text PRIMARY KEY NOT NULL,
	"objective" text NOT NULL,
	"constraints" jsonb,
	"status" text DEFAULT 'created' NOT NULL,
	"created_at" timestamp DEFAULT now() NOT NULL,
	"updated_at" timestamp DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "runs" (
	"id" text PRIMARY KEY NOT NULL,
	"plan_id" text DEFAULT '' NOT NULL,
	"status" text DEFAULT 'created' NOT NULL,
	"attempt" integer DEFAULT 0 NOT NULL,
	"payload" jsonb,
	"created_at" timestamp DEFAULT now() NOT NULL,
	"updated_at" timestamp DEFAULT now() NOT NULL,
	"finished_at" timestamp
);
--> statement-breakpoint
CREATE TABLE "tasks" (
	"id" text PRIMARY KEY NOT NULL,
	"position" geometry(point) NOT NULL,
	"priority" text DEFAULT 'medium' NOT NULL,
	"payload_weight" real NOT NULL,
	"time_limit" integer,
	"status" text DEFAULT 'pending' NOT NULL
);
--> statement-breakpoint
CREATE TABLE "uavs" (
	"id" text PRIMARY KEY NOT NULL,
	"position" geometry(point) NOT NULL,
	"speed" real NOT NULL,
	"max_payload" real NOT NULL,
	"battery" real NOT NULL,
	"status" text DEFAULT 'idle' NOT NULL
);
--> statement-breakpoint
CREATE TABLE "worker_executions" (
	"id" text PRIMARY KEY NOT NULL,
	"run_id" text NOT NULL,
	"task_id" text NOT NULL,
	"capability" text NOT NULL,
	"worker_type" text NOT NULL,
	"attempt" integer DEFAULT 0 NOT NULL,
	"status" text NOT NULL,
	"duration_ms" integer,
	"feedback_type" text,
	"error_code" text,
	"details" jsonb,
	"created_at" timestamp DEFAULT now() NOT NULL
);

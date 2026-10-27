export type User = {
	id: number;
	name: string;
	email: string;
	initials: string | null;
	designation: string | null;
	roles: string[];
	capabilities: string[];
};

export type Equipment = {
	id: number;
	name: string;
	category: 'hardware' | 'software' | 'av' | 'facility';
	quantity: number;
	status: string;
};

export type Venue = {
	id: number;
	code: string;
	name: string;
	type: 'lab' | 'coe' | 'seminar_hall';
	block: string | null;
	department: string | null;
	capacity: number;
	byod: boolean;
	needs_hod_approval: boolean;
	in_charge: { id: number; name: string; email: string } | null;
};

export type VenueDetail = Venue & { equipment: Equipment[]; aliases: string[] };

export const ROLE_LABELS: Record<string, string> = {
	faculty: 'Faculty',
	technician: 'Lab Technician',
	incharge: 'Venue In-charge',
	oa: 'OA / DEO',
	hod: 'HOD',
	director: 'Director IM'
};

export const VENUE_TYPE_LABELS: Record<Venue['type'], string> = {
	lab: 'Labs',
	coe: 'Centres of Excellence',
	seminar_hall: 'Seminar Halls'
};

export type StatusPeriod = {
	id: number;
	status: 'maintenance' | 'renovation' | 'closed';
	from_date: string;
	to_date: string | null;
	reason: string | null;
};

export type SeasonalRule = {
	id: number;
	start_month: number;
	end_month: number;
	kind: 'blocked' | 'soft_warning';
	reason: string;
};

export type VenueFull = VenueDetail & {
	technician: { id: number; name: string; email: string } | null;
	notes: string | null;
	status_periods: StatusPeriod[];
	seasonal_rules: SeasonalRule[];
	can_edit: boolean;
	can_update_equipment: boolean;
	can_edit_restricted: boolean;
};

export type Block = {
	start: string;
	end: string;
	kind: string;
	label: string;
	hard: boolean;
};
export type Notice = { kind: string; message: string };

export type VenueDay = {
	code: string;
	name: string;
	type: Venue['type'];
	capacity: number;
	byod: boolean;
	blocks: Block[];
	warnings: Notice[];
};

export type DayAvailability = {
	date: string;
	open_from: string | null;
	open_to: string | null;
	slot_minutes: number;
	venues: VenueDay[];
};

export const MONTHS = [
	'Jan',
	'Feb',
	'Mar',
	'Apr',
	'May',
	'Jun',
	'Jul',
	'Aug',
	'Sep',
	'Oct',
	'Nov',
	'Dec'
];

export type ClassSlot = {
	id: number;
	section: string;
	term: string;
	venue: string;
	weekday: string;
	start: string;
	end: string;
	subject_code: string;
	subject_name: string;
	faculty_name: string | null;
	batch: string;
};

export type TimetableHeader = {
	dept: string | null;
	year: string | null;
	section: string | null;
	term_name: string | null;
	valid_from: string | null;
	valid_to: string | null;
	class_advisor: string | null;
};

export type ParsedSlot = {
	weekday: string;
	start: string;
	end: string;
	subject_code: string;
	subject_name: string;
	faculty_name: string;
	batch: string;
	venue: string;
	venue_code?: string | null;
	issues?: string[];
};

export type TimetableUpload = {
	id: number;
	filename: string;
	status: 'parsed' | 'committed';
	uploaded_at: string;
	header: TimetableHeader;
	periods: { no: number; start: string; end: string }[];
	grid: Record<string, (string | null)[]>;
	slots: ParsedSlot[];
	problems: string[];
	can_commit: boolean;
};

export type UploadBrief = {
	id: number;
	filename: string;
	status: 'parsed' | 'committed';
	uploaded_at: string;
	section: string | null;
	slots: number;
	can_commit: boolean;
};

export type Section = {
	id: number;
	label: string;
	dept: string;
	year: string;
	section: string;
	advisor: string | null;
	lab_slots: number;
};

export const WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

// Bookings -----------------------------------------------------------------------------------

export type VenueBrief = { code: string; name: string; type: Venue['type']; capacity: number };

export type RelocationOption = {
	code: string;
	name: string;
	capacity: number;
	software_match: number;
	missing_software: string[];
};

export type ClassClash = {
	slot_id: number;
	date: string;
	label: string;
	subject_name: string;
	faculty_name: string | null;
	start: string;
	end: string;
	batch_size: number;
	options: RelocationOption[];
};

export type BookingCheck = {
	venue: VenueBrief;
	outcome: 'free' | 'displace' | 'waitlist' | 'blocked';
	days: string[];
	blocked: Block[];
	taken: Block[];
	clashes: ClassClash[];
	warnings: Notice[];
	alternatives: VenueBrief[];
};

export type Move = {
	slot_id: number;
	date: string;
	action: 'relocated' | 'byod_classroom';
	venue_code?: string | null;
};

export type Booking = {
	id: number;
	ref: string;
	title: string;
	event_type: string;
	description: string | null;
	requirements: string | null;
	expected_count: number;
	venue: VenueBrief;
	requester: string;
	requester_email: string;
	status: string;
	start: string;
	end: string;
	occurrences: { start: string; end: string }[];
	approvals: {
		step: string;
		decision: string;
		approver: string | null;
		comment: string | null;
		decided_at: string;
	}[];
	moves: {
		slot_id: number;
		date: string;
		label: string;
		time: string;
		action: string;
		venue: string | null;
		faculty_name: string | null;
	}[];
	steps: string[];
	waitlist_position: number | null;
	offer_expires_at: string | null;
	cancel_reason: string | null;
	parent_ref: string | null;
	created_at: string;
	can_cancel: boolean;
	can_reschedule: boolean;
	can_approve: boolean;
};

export type ApprovalItem = {
	booking: Booking;
	step: string;
	notes: string[];
	waiting_behind: number;
};

export type AppNotification = {
	id: number;
	kind: string;
	message: string;
	link: string | null;
	created_at: string;
	read_at: string | null;
};

export const STATUS_LABELS: Record<string, string> = {
	pending_incharge: 'Waiting for in-charge',
	pending_hod: 'Waiting for HOD',
	confirmed: 'Confirmed',
	rejected: 'Rejected',
	cancelled: 'Cancelled',
	waitlisted: 'On the waitlist',
	offered: 'Slot offered: confirm now',
	expired: 'Offer expired'
};

export const STATUS_TONE: Record<string, string> = {
	pending_incharge: 'bg-warning/20 text-warning',
	pending_hod: 'bg-warning/20 text-warning',
	confirmed: 'bg-success/15 text-success',
	rejected: 'bg-danger/15 text-danger',
	cancelled: 'bg-muted/20 text-muted',
	waitlisted: 'bg-accent-soft text-accent',
	offered: 'bg-accent text-accent-fg',
	expired: 'bg-muted/20 text-muted'
};

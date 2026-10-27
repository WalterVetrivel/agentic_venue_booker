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
  category: "hardware" | "software" | "av" | "facility";
  quantity: number;
  status: string;
};

export type Venue = {
  id: number;
  code: string;
  name: string;
  type: "lab" | "coe" | "seminar_hall";
  block: string | null;
  department: string | null;
  capacity: number;
  byod: boolean;
  needs_hod_approval: boolean;
  in_charge: { id: number; name: string; email: string } | null;
};

export type VenueDetail = Venue & { equipment: Equipment[]; aliases: string[] };

export const ROLE_LABELS: Record<string, string> = {
  faculty: "Faculty",
  technician: "Lab Technician",
  incharge: "Venue In-charge",
  oa: "OA / DEO",
  hod: "HOD",
  director: "Director IM",
};

export const VENUE_TYPE_LABELS: Record<Venue["type"], string> = {
  lab: "Labs",
  coe: "Centres of Excellence",
  seminar_hall: "Seminar Halls",
};

export type StatusPeriod = {
  id: number;
  status: "maintenance" | "renovation" | "closed";
  from_date: string;
  to_date: string | null;
  reason: string | null;
};

export type SeasonalRule = {
  id: number;
  start_month: number;
  end_month: number;
  kind: "blocked" | "soft_warning";
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
  type: Venue["type"];
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
  "Jan",
  "Feb",
  "Mar",
  "Apr",
  "May",
  "Jun",
  "Jul",
  "Aug",
  "Sep",
  "Oct",
  "Nov",
  "Dec",
];

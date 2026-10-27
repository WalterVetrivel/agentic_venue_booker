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

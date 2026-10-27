export type NavItem = {
	href: string;
	label: string;
	icon: string;
	/** Shown when the user has any of these capabilities. Empty means everyone. */
	anyOf: string[];
	/** One line for the home page card. */
	blurb: string;
};

export const NAV: NavItem[] = [
	{ href: '/', label: 'Home', icon: 'home', blurb: '', anyOf: [] },
	{
		href: '/availability',
		label: 'Availability',
		icon: 'calendar',
		blurb: 'See which venues are free on a day',
		anyOf: []
	},
	{
		href: '/venues',
		label: 'Venues',
		icon: 'building',
		blurb: 'Labs, halls and what they have',
		anyOf: []
	},
	{
		href: '/book',
		label: 'Book a venue',
		icon: 'plus',
		blurb: 'Request a lab, centre or hall',
		anyOf: ['book']
	},
	{
		href: '/bookings',
		label: 'My bookings',
		icon: 'list',
		blurb: 'Your requests and their status',
		anyOf: ['book']
	},
	{
		href: '/approvals',
		label: 'Approvals',
		icon: 'check',
		blurb: 'Requests waiting for your decision',
		anyOf: ['approve_own_venues', 'approve_cse_venues', 'approve_all', 'approve_displacement']
	},
	{
		href: '/timetables',
		label: 'Timetables',
		icon: 'table',
		blurb: 'Upload and review class timetables',
		anyOf: ['upload_timetables']
	},
	{
		href: '/documents',
		label: 'Past events',
		icon: 'file',
		blurb: 'Circulars and reports of past events',
		anyOf: ['book', 'upload_documents', 'notified_of_events']
	},
	{
		href: '/reports',
		label: 'Reports',
		icon: 'chart',
		blurb: 'Utilisation, events and turnaround',
		anyOf: ['reports_own', 'reports_cse', 'reports_all']
	},
	{
		href: '/settings',
		label: 'Settings',
		icon: 'gear',
		blurb: 'Assistant provider and models',
		anyOf: ['manage_settings']
	}
];

export function visibleNav(capabilities: string[]): NavItem[] {
	return NAV.filter((n) => n.anyOf.length === 0 || n.anyOf.some((c) => capabilities.includes(c)));
}

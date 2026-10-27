export type NavItem = {
	href: string;
	label: string;
	icon: string;
	/** Shown when the user has any of these capabilities. Empty means everyone. */
	anyOf: string[];
	phase?: number;
};

export const NAV: NavItem[] = [
	{ href: '/', label: 'Home', icon: 'home', anyOf: [] },
	{ href: '/availability', label: 'Availability', icon: 'calendar', anyOf: [] },
	{ href: '/venues', label: 'Venues', icon: 'building', anyOf: [] },
	{
		href: '/book',
		label: 'Book a venue',
		icon: 'plus',
		anyOf: ['book']
	},
	{
		href: '/bookings',
		label: 'My bookings',
		icon: 'list',
		anyOf: ['book']
	},
	{
		href: '/approvals',
		label: 'Approvals',
		icon: 'check',
		anyOf: ['approve_own_venues', 'approve_cse_venues', 'approve_all', 'approve_displacement']
	},
	{
		href: '/timetables',
		label: 'Timetables',
		icon: 'table',
		anyOf: ['upload_timetables']
	},
	{
		href: '/documents',
		label: 'Circulars & reports',
		icon: 'file',
		anyOf: ['upload_documents'],
		phase: 4
	},
	{
		href: '/reports',
		label: 'Reports',
		icon: 'chart',
		anyOf: ['reports_own', 'reports_cse', 'reports_all'],
		phase: 6
	},
	{
		href: '/settings',
		label: 'Settings',
		icon: 'gear',
		anyOf: ['manage_settings'],
		phase: 5
	}
];

export function visibleNav(capabilities: string[]): NavItem[] {
	return NAV.filter((n) => n.anyOf.length === 0 || n.anyOf.some((c) => capabilities.includes(c)));
}

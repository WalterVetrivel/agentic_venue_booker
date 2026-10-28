// Quick replies offered under the assistant's last message.

const OPENERS =
	/^(shall|should|would|will|do|does|did|can|could|is|are|was|were|may|might|want|need|have|has|ok|okay)\b/i;
const ASKS = /\b(would you like|do you want|want me to|like me to|shall i|should i|can i|may i)\b/i;
const LEADS = /^(if so|if yes|also|and|so|then|alternatively|otherwise|meanwhile)[,:]?\s+/i;

/** The question the reply ends on, if its last words ask one. */
function closingQuestion(text: string): string | null {
	const plain = text
		.replace(/```[\s\S]*?```/g, ' ')
		.replace(/[*_`>#]+/g, '')
		.replace(/\[([^\]]*)\]\([^)]*\)/g, '$1')
		.trim();
	const end = plain.lastIndexOf('?');
	// Only when the question closes the reply (a short sign-off after it is fine).
	if (end < 0 || plain.length - end > 60) return null;
	const before = plain.slice(0, end);
	const start = Math.max(
		before.lastIndexOf('. '),
		before.lastIndexOf('! '),
		before.lastIndexOf('? '),
		before.lastIndexOf('\n')
	);
	return before.slice(start + 1).trim() + '?';
}

/** "Yes" and "No" replies when the assistant ends on a yes/no question; none otherwise. */
export function yesNoReplies(text: string): string[] {
	let q = closingQuestion(text);
	if (!q) return [];
	while (LEADS.test(q)) q = q.replace(LEADS, '');
	// "CC5 or CC6?" is a choice, not a yes/no question.
	if (/\bor\b/i.test(q) && !/\bor not\b/i.test(q)) return [];
	if (!OPENERS.test(q) && !ASKS.test(q)) return [];
	return ['Yes, please', 'No, thanks'];
}

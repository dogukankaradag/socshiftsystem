import { PRIORITY_LABEL, Priority } from '../api/client';

const CLASSES: Record<Priority, string> = {
  low: 'bg-green-100 text-green-800',
  medium: 'bg-yellow-100 text-yellow-800',
  high: 'bg-orange-100 text-orange-800',
  critical: 'bg-red-100 text-red-800',
};

export default function PriorityBadge({ priority }: { priority: Priority }) {
  return (
    <span className={`pill ${CLASSES[priority]}`}>
      {PRIORITY_LABEL[priority].toUpperCase()}
    </span>
  );
}

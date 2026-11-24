import type {Ambulance, Explanation, Scenario} from './types';

export type MapMode = 'operational' | 'routing' | 'truth';
export const modes: Record<MapMode, string> = {
  operational: 'Operational', routing: 'Ambulance Routing', truth: 'Simulation Truth',
};

export function zoneFor(node: string | undefined, scenario: Scenario | undefined) {
  const point = scenario?.graph.nodes.find(item => item.id === node);
  if (!point || !scenario) return 'Unassigned';
  const middle = Math.max(...scenario.graph.nodes.map(item => item.y)) / 2;
  return point.y < middle ? 'North' : point.y > middle ? 'South' : 'Central';
}

export function filterFleet(fleet: Ambulance[], query: string, zone: string, scenario?: Scenario) {
  return fleet.filter(vehicle => vehicle.id.toLowerCase().includes(query.trim().toLowerCase())
    && (zone === 'All zones' || zoneFor(vehicle.node, scenario) === zone));
}

export function routingEdges(explanation: Explanation | null | undefined) {
  const live = explanation?.liveEdges ?? [];
  const fallback = Object.entries(explanation?.roads ?? {})
    .filter(([, estimate]) => estimate.source === 'HISTORICAL_FALLBACK').map(([id]) => id);
  return {live: live.filter(id => !fallback.includes(id)), fallback};
}

export const clock = (seconds: number) =>
  `${Math.floor(seconds / 60).toString().padStart(2, '0')}:${Math.floor(seconds % 60).toString().padStart(2, '0')}`;
export const readable = (text: string) => text.toLowerCase().replaceAll('_', ' ');

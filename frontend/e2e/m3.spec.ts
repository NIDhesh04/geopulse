import {test, expect} from '@playwright/test';
import type {Ambulance, Snapshot} from '../src/types';

test('fleet map modes keep physical incidents separate from driver report review', async ({page, context}) => {
  const errors:string[] = [];
  page.on('pageerror',error=>errors.push(error.message));
  await page.goto('/');
  await page.getByLabel('Scenario for next run').selectOption('fleet-conflict-5x5');
  await page.getByRole('button',{name:'Create run',exact:true}).click();
  await expect(page.locator('.ambulance-card')).toHaveCount(10);
  await page.getByLabel('Search fleet').fill('008');
  await page.getByLabel('Zone',{exact:true}).selectOption('South');
  await expect(page.locator('.ambulance-card')).toHaveCount(1);
  await page.getByRole('button',{name:/AMB-008/}).click();
  await page.getByRole('button',{name:'Activate mission',exact:true}).click();
  await expect(page.locator('.ambulance-card').first()).toContainText('at junction');
  await page.getByLabel('Search fleet').clear();
  await page.getByLabel('Zone',{exact:true}).selectOption('All zones');
  await page.getByRole('button',{name:/AMB-001 idle/i}).click();
  await page.getByRole('button',{name:'Activate mission',exact:true}).click();
  await page.getByRole('button',{name:'Ambulance Routing',exact:true}).click();
  await expect(page.locator('.candidate.winner')).toBeVisible();
  const runId = await page.evaluate(()=>localStorage.getItem('geopulse.run'));
  const snapshot = async () => (await page.request.get(`/api/runs/${runId}/snapshot`)).json() as Promise<Snapshot>;
  const blocked = (await snapshot()).ambulance.route[0];
  await page.getByRole('button',{name:'Simulation Truth',exact:true}).click();
  await page.getByLabel('Road segment').selectOption(blocked);
  await page.getByRole('button',{name:'Apply road condition'}).click();
  await expect(page.getByText('entry closed',{exact:true})).toBeVisible();
  await expect(page.getByText(/Actual occupancy/)).toBeVisible();
  await page.getByRole('button',{name:'Operational',exact:true}).click();
  await expect(page.getByText('No confirmed closure',{exact:true})).toBeVisible();
  expect((await snapshot()).reportedClosures).toEqual([]);
  await page.getByRole('button',{name:'Step 1s'}).click();
  await expect(page.getByText('Priority granted',{exact:true})).toBeVisible();
  const driver = await context.newPage();
  driver.on('pageerror',error=>errors.push(error.message));
  await driver.setViewportSize({width:390,height:844});
  await driver.goto((await page.getByRole('link',{name:'Open Driver Navigation'}).getAttribute('href'))!);
  await expect(driver.getByRole('heading',{name:'Driver Navigation'})).toBeVisible();
  await expect(driver.getByText('Priority granted',{exact:true})).toBeVisible();
  await expect(driver.getByText('Following ambulance',{exact:true})).toBeVisible();
  await expect.poll(async()=>Number(await driver.locator('.map-surface').getAttribute('data-road-count'))).toBeGreaterThan(0);
  const map = (await driver.locator('canvas.maplibregl-canvas').boundingBox())!;
  await driver.mouse.move(map.x+map.width/2,map.y+map.height/2);
  await driver.mouse.down();
  await driver.mouse.move(map.x+map.width/2+75,map.y+map.height/2,{steps:7});
  await driver.mouse.up();
  await driver.getByRole('button',{name:'Recenter',exact:true}).click();
  await expect(driver.getByText('Following ambulance',{exact:true})).toBeVisible();
  await expect(driver.getByRole('heading',{name:'Estimated arrival'})).toBeVisible();
  await page.getByRole('button',{name:'Step 1s'}).click();
  await expect.poll(async()=>(await snapshot()).ambulance.edge).not.toBeNull();
  const current = (await snapshot()).ambulance.edge!;
  await expect(driver.getByText(`Current road ${current}`,{exact:true})).toBeVisible();
  const reportButton = driver.getByRole('button',{name:'Report Obstruction',exact:true});
  expect((await reportButton.boundingBox())?.height).toBeGreaterThanOrEqual(44);
  expect(await driver.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await reportButton.click();
  await expect(driver.getByLabel('Road segment')).toHaveValue(current);
  await driver.getByRole('button',{name:'Submit report',exact:true}).click();
  await expect(driver.getByText('Awaiting operator review',{exact:true})).toBeVisible();
  await expect(page.getByText(new RegExp(current+'.*Awaiting operator review'))).toBeVisible();
  expect((await snapshot()).reportedClosures).toEqual([]);
  await page.getByRole('button',{name:'Confirm',exact:true}).click();
  await expect.poll(async()=>(await snapshot()).reportedClosures).toEqual([current]);
  await expect(driver.getByText('Report confirmed',{exact:true})).toBeVisible();
  await page.getByRole('button',{name:'Suspend priority',exact:true}).click();
  await expect(driver.getByText('Priority suspended',{exact:true})).toBeVisible();
  expect(errors).toEqual([]);
});

test('driver explains red waiting, missing and exceeded ETA, arrival, and stale readings', async ({page,context}) => {
  const runId = '00000000-0000-0000-0000-000000000041';
  const vehicle: Ambulance = {id:'AMB-001',status:'AT_JUNCTION',node:'n00_00',edge:null,progress:0,
    destination:'n04_04',route:['n00_00_n00_01'],activatedAt:1,arrivedAt:null,replans:0,reroutes:0,reason:null,initialEta:90,estimatedArrival:90};
  let tick = 10;
  let priority = 'REQUESTED';
  await page.route(`**/api/runs/${runId}/snapshot`,route=>route.fulfill({json:{
    runId, scenarioId:'fleet-conflict-5x5', stateRevision:'3', latestEventSequence:'0', simulationTimeSeconds:tick,
    paused:true,speed:1,horizon:'2',runStatus:'PAUSED',ambulance:vehicle,fleet:[vehicle],reportedClosures:[],priorityEnabled:true,
    traffic:{priority,signals:{n00_00:{phase:'ALL_RED',permissions:[0],approaches:['station-entry:n00_00']}}},
  }}));
  await page.route(`**/api/runs/${runId}/events?*`,route=>route.fulfill({json:[]}));
  await page.route(`**/api/runs/${runId}/ambulances/AMB-001/snapshot`,route=>route.fulfill({json:{
    ambulance:vehicle,priority,prioritySuspended:false,junctionWait:0,explanation:null,
  }}));
  const reload = async () => {
    await page.goto(`/driver?run=${runId}&ambulance=AMB-001`);
    await expect(page.getByText('Connected',{exact:true})).toBeVisible();
  };
  await reload();
  await expect(page.getByText('Priority requested',{exact:true})).toBeVisible();
  await expect(page.getByText('Waiting at red light',{exact:true})).toBeVisible();
  await expect(page.locator('.driver-alert')).toHaveCount(0);
  await expect(page.getByText('1m 20s',{exact:true})).toBeVisible();
  await expect(page.getByText('00:01:30',{exact:true})).toBeVisible();
  await context.setOffline(true);
  await expect(page.getByText('Stale · Last confirmed estimate')).toBeVisible();
  await expect(page.getByText('1m 20s',{exact:true})).toBeVisible();
  await context.setOffline(false);

  tick=90; priority='DOWNSTREAM_BLOCKED';
  await reload();
  await expect(page.getByRole('heading',{name:'Estimate exceeded'})).toBeVisible();
  await expect(page.getByText('Downstream blocked',{exact:true})).toBeVisible();
  vehicle.status='STOPPED';vehicle.estimatedArrival=null;vehicle.reason='DESTINATION_UNREACHABLE';vehicle.reroutes=1;
  await reload();
  await expect(page.getByRole('heading',{name:'ETA unavailable'})).toBeVisible();
  await expect(page.getByRole('alert')).toContainText('No feasible route');
  await expect(page.getByText('Route updated · Reroutes 1')).toBeVisible();
  vehicle.status='ARRIVED';vehicle.arrivedAt=97;vehicle.reason=null;tick=97;
  await reload();
  await expect(page.getByRole('heading',{name:'Journey completed'})).toBeVisible();
  await expect(page.getByText('1m 36s',{exact:true})).toBeVisible();
});

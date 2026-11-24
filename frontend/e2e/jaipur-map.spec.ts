import {expect,test} from '@playwright/test';

test('Jaipur map and driver voice use a server-authoritative mission',async({page})=>{
  const errors:string[]=[];
  page.on('pageerror',error=>errors.push(error.stack??error.message));
  await page.emulateMedia({reducedMotion:'reduce'});
  await page.goto('/welcome');
  await expect(page.getByRole('radio',{name:/Jaipur · SMS Hospital corridor/})).toBeChecked();
  await expect(page.getByRole('link',{name:'© OpenStreetMap'})).toBeVisible();
  await page.getByRole('link',{name:'Open Police Control Room'}).click();
  await expect(page.getByLabel('Scenario for next run')).toHaveValue('jaipur-sms-corridor');
  await page.getByRole('button',{name:'Create run',exact:true}).click();
  await page.getByRole('button',{name:'Activate mission',exact:true}).click();
  await page.getByRole('button',{name:'Ambulance Routing',exact:true}).click();
  await expect(page.locator('.candidate.winner')).toBeVisible();
  await expect.poll(async()=>Number(await page.locator('.map-surface').getAttribute('data-road-count'))).toBeGreaterThan(0);
  const tilt=page.getByRole('button',{name:'3D view'});
  const allStreets=page.getByRole('button',{name:'All Streets'});
  await expect(allStreets).toHaveAttribute('aria-pressed','true');
  await allStreets.click();
  await expect(allStreets).toHaveAttribute('aria-pressed','false');
  await page.getByRole('button',{name:'Corridor',exact:true}).click();
  await page.getByRole('button',{name:'City',exact:true}).click();
  await allStreets.click();
  await expect(allStreets).toHaveAttribute('aria-pressed','true');
  await expect(tilt).toHaveAttribute('aria-pressed','true');
  await tilt.click();
  await expect(tilt).toHaveAttribute('aria-pressed','false');
  await page.addInitScript(()=>{
    Object.defineProperty(window.speechSynthesis,'speak',{value:(cue:SpeechSynthesisUtterance)=>{
      document.documentElement.dataset.lastSpoken=cue.text;
    }});
  });
  const driverUrl=(await page.getByRole('link',{name:'Open Driver Navigation'}).getAttribute('href'))!;
  await page.setViewportSize({width:390,height:844});
  await page.goto(driverUrl);
  await expect(page.getByRole('heading',{name:'Estimated arrival'})).toBeVisible();
  await page.getByRole('button',{name:'Voice off'}).click();
  await expect(page.getByRole('button',{name:'Voice on'})).toHaveAttribute('aria-pressed','true');
  await expect(page.locator('html')).toHaveAttribute('data-last-spoken',/onto/);
  await expect(page.getByText('Jaipur · Simulated traffic and signals')).toBeVisible();
  expect(errors).toEqual([]);
});

test('Jaipur corridor remains visible when city context tiles are unavailable',async({page})=>{
  await page.route('https://tiles.openfreemap.org/**',route=>route.abort());
  await page.goto('/welcome');
  await expect(page.getByText(/Context tiles unavailable/)).toBeVisible();
  await expect.poll(async()=>Number(await page.locator('.map-surface').getAttribute('data-road-count'))).toBeGreaterThan(0);
  await expect(page.locator('.map-failure')).toHaveCount(0);
});

import {test,expect} from '@playwright/test';

test('landing scenario selection opens compact setup with a live network preview', async ({page})=>{
  await page.setViewportSize({width:360,height:800});
  await page.goto('/welcome');
  await expect(page.getByRole('heading',{name:'Simulate ambulance routing and signal priority'})).toBeVisible();
  const choice=page.getByRole('radio',{name:/Traffic and signals/});
  await choice.focus();
  await page.keyboard.press('Space');
  await expect(choice).toBeChecked();
  await expect.poll(async()=>Number(await page.locator('.map-surface').getAttribute('data-road-count'))).toBeGreaterThan(0);
  await page.getByRole('link',{name:'Open Police Control Room'}).click();
  await expect(page.getByLabel('Scenario for next run')).toHaveValue('traffic-signals-5x5');
  await expect(page.getByRole('button',{name:'Close fleet'})).toBeFocused();
  await page.keyboard.press('Escape');
  await expect(page.getByRole('button',{name:'Fleet',exact:true})).toBeFocused();
});

test('all control room breakpoints preserve keyboard selection and drawer focus', async ({page})=>{
  await page.setViewportSize({width:1280,height:900});
  await page.goto('/');
  const layout=page.locator('main[data-layout]');
  const fleet=page.locator('#panel-fleet');
  const inspector=page.locator('#panel-inspector');
  const activity=page.locator('#panel-activity');
  await expect(layout).toHaveAttribute('data-layout','desktop');
  await expect(fleet).toBeVisible();
  await expect(inspector).toBeVisible();
  const contrast = await page.evaluate(()=>{
    function luminance(rgb:string) {
      const [r,g,b]=(rgb.match(/[\d.]+/g)??[]).slice(0,3).map(value=>{
        const channel=Number(value)/255;
        return channel<=0.04045?channel/12.92:((channel+0.055)/1.055)**2.4;
      });
      return 0.2126*r+0.7152*g+0.0722*b;
    }
    return ['.fleet-panel .secondary.full','.mode-switch .active','.inspector'].map(selector=>{
      const style=getComputedStyle(document.querySelector(selector)!);
      const colors=[luminance(style.color),luminance(style.backgroundColor)].sort((a,b)=>b-a);
      return (colors[0]+0.05)/(colors[1]+0.05);
    });
  });
  contrast.forEach(ratio=>expect(ratio).toBeGreaterThanOrEqual(4.5));
  await expect(page.locator('.clock strong')).toHaveCSS('font-variant-numeric','tabular-nums');
  await page.getByLabel('Scenario for next run').selectOption('fleet-conflict-5x5');
  await page.getByRole('button',{name:'Create run',exact:true}).click();
  await expect(fleet.locator('.ambulance-card')).toHaveCount(10);
  await expect.poll(async()=>Number(await page.locator('.map-surface').getAttribute('data-road-count'))).toBeGreaterThan(0);
  await page.emulateMedia({reducedMotion:'reduce'});
  const station=page.getByText('Station 01',{exact:true});
  const initialCamera=await station.getAttribute('style');
  const distant=fleet.getByRole('button',{name:/AMB-008/});
  await distant.focus();
  await page.keyboard.press('Enter');
  await expect(distant).toHaveAttribute('aria-pressed','true');
  await expect(station).toHaveAttribute('style',initialCamera!);
  await page.getByRole('button',{name:'Locate',exact:true}).click();
  await expect(station).not.toHaveAttribute('style',initialCamera!);
  await expect(fleet.getByRole('button',{name:/AMB-008/})).toHaveAttribute('aria-pressed','true');

  await page.setViewportSize({width:1279,height:900});
  await expect(layout).toHaveAttribute('data-layout','tablet');
  await expect(fleet).toBeHidden();
  await expect(activity).toBeVisible();
  const fleetTrigger=page.getByRole('button',{name:'Fleet',exact:true});
  const inspectorTrigger=page.getByRole('button',{name:'Inspector',exact:true});
  await fleetTrigger.focus();
  await page.keyboard.press('Enter');
  await expect(page.getByRole('button',{name:'Close fleet'})).toBeFocused();
  const ambulance=fleet.getByRole('button',{name:/AMB-008/});
  await ambulance.focus();
  await page.keyboard.press('Space');
  await expect(ambulance).toHaveAttribute('aria-pressed','true');
  await page.keyboard.press('Escape');
  await expect(fleet).toBeHidden();
  await expect(fleetTrigger).toBeFocused();

  await page.setViewportSize({width:900,height:850});
  await expect(layout).toHaveAttribute('data-layout','tablet');
  await inspectorTrigger.focus();
  await page.keyboard.press('Enter');
  await expect(inspector).toHaveCSS('position','absolute');
  await expect(inspector.getByText('AMB-008',{exact:true})).toBeVisible();
  await page.getByLabel('Inspect junction').focus();
  await page.keyboard.press('ArrowDown');
  await expect(inspector.getByRole('heading',{name:'Junction n00_00'})).toBeVisible();
  await page.getByLabel('Road segment').focus();
  await page.keyboard.press('ArrowDown');
  await expect(inspector.getByText('No confirmed closure',{exact:true})).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(inspectorTrigger).toBeFocused();

  await page.setViewportSize({width:899,height:850});
  await expect(layout).toHaveAttribute('data-layout','compact');
  await expect(activity).toBeHidden();
  await page.setViewportSize({width:360,height:800});
  await page.emulateMedia({reducedMotion:'reduce'});
  await fleetTrigger.click();
  await expect(fleet).toHaveCSS('animation-name','none');
  await expect(fleet).toHaveCSS('position','fixed');
  await inspectorTrigger.click();
  await expect(fleet).toBeHidden();
  await expect(inspector).toBeVisible();
  const activityTrigger=page.getByRole('button',{name:'Run activity',exact:true});
  await activityTrigger.click();
  await expect(inspector).toBeHidden();
  await expect(activity).toBeVisible();
  await expect(page.getByRole('button',{name:'Close run activity'})).toBeFocused();
  await page.keyboard.press('Escape');
  await expect(activityTrigger).toBeFocused();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
});

test('incoming events preserve the event reader position and keyboard focus', async ({page})=>{
  await page.goto('/');
  await page.getByRole('button',{name:'Create run',exact:true}).click();
  await expect(page.locator('.connection')).toHaveText('Connected');
  const id=await page.evaluate(()=>localStorage.getItem('geopulse.run'));
  const command=()=>page.request.post(`/api/runs/${id}/commands`,{data:{
    commandId:crypto.randomUUID(),type:'STEP',payload:{},
  }});
  for(let index=0;index<12;index++)expect((await command()).ok()).toBe(true);
  await page.getByRole('button',{name:'Events',exact:true}).click();
  const log=page.getByRole('log',{name:'Recorded events'});
  await expect(log.locator('.event')).toHaveCount(12);
  await log.focus();
  await log.evaluate(node=>{node.scrollTop=70;});
  expect((await command()).ok()).toBe(true);
  await expect(log.locator('.event')).toHaveCount(13);
  await expect(log).toBeFocused();
  expect(await log.evaluate(node=>node.scrollTop)).toBe(70);
});

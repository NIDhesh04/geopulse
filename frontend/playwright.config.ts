import {defineConfig} from '@playwright/test';
export default defineConfig({testDir:'./e2e',workers:1,timeout:45000,use:{baseURL:'http://127.0.0.1:5173',viewport:{width:1440,height:1000},launchOptions:{args:['--enable-unsafe-swiftshader']},screenshot:'only-on-failure'},reporter:'list'});

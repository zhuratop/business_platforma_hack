import {defineConfig} from '@playwright/test';
export default defineConfig({testDir:'tests',timeout:480000,workers:1,retries:0,reporter:'list',outputDir:'../runtime/browser-results',use:{baseURL:'http://127.0.0.1:8000',headless:true,channel:'msedge',viewport:{width:1512,height:1000},screenshot:'only-on-failure'}});

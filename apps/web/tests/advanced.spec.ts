import { test, expect } from '@playwright/test';
import path from 'node:path';

test('FIT dynamics, evidence coaching, benchmark targets and distance interval editing', async ({ page }) => {
  test.setTimeout(60000);
  await page.goto('/');
  await page.getByRole('button', { name: '처음 오셨나요? 회원가입' }).click();
  await page.getByLabel('이름', { exact: true }).fill('FIT 검증 러너');
  await page.getByLabel('이메일', { exact: true }).fill(`fit-${Date.now()}-${test.info().project.name}@example.com`);
  await page.getByLabel('비밀번호', { exact: true }).fill('fixture-test-password');
  await page.getByRole('button', { name: '회원가입', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'FIT 검증 러너님, 오늘도 나의 페이스로.' })).toBeVisible();
  const nav = page.getByRole('navigation', { name: test.info().project.name.startsWith('mobile') ? '모바일 메뉴' : '주 메뉴' });
  await nav.getByRole('button', { name: '설정', exact: true }).click();
  await page.getByLabel('설정할 최대심박 (bpm)').fill('190');
  await page.getByLabel('실제 5K 기록 (분)').fill('25');
  await page.getByLabel('5K 기록 날짜').fill(new Date().toISOString().slice(0, 10));
  await page.getByRole('button', { name: '훈련 기준 저장' }).click();
  await expect(page.getByText('훈련 기준을 저장했습니다.', { exact: false })).toBeVisible();
  await nav.getByRole('button', { name: '대시보드', exact: true }).click();
  await page.getByLabel('GPX 업로드', { exact: true }).setInputFiles(path.resolve('../../samples/running-dynamics.fit'));
  await expect(page.getByText('분석 완료', { exact: true })).toBeVisible({ timeout: 30000 });
  await expect(page.locator('.stat-item').filter({ has: page.getByText('평균 케이던스', { exact: true }) })).toContainText('166');
  await expect(page.locator('.stat-item').filter({ has: page.getByText('평균 보폭', { exact: true }) })).toContainText('0.96');
  await expect(page.getByRole('heading', { name: 'AI 코치 피드백' })).toBeVisible();
  await page.getByLabel('훈련 의도', { exact: true }).selectOption('easy');
  await page.getByLabel('체감 강도 RPE (1–10)').fill('8');
  await page.getByText('가민 추가 정보 직접 기록', { exact: true }).click();
  await page.getByLabel('바디 배터리 순 영향 (점)').fill('-9');
  await page.getByRole('button', { name: '훈련 의도 저장 · 코칭 갱신' }).click();
  await expect(page.locator('.stat-item').filter({ has: page.getByText('바디 배터리 순 영향', { exact: true }) })).toContainText('-9');
  await expect(page.getByText('저강도 훈련으로 기록했지만 체감 강도는 8/10입니다.', { exact: false })).toBeVisible();
  await page.getByLabel('그래프 가로축').selectOption('distance');
  await page.getByLabel('페이스 또는 속도').selectOption('speed');
  await expect(page.getByRole('img', { name: '속도 실제 기록 그래프' })).toBeVisible();
  await page.getByRole('button', { name: '나만 보는 러닝 경로' }).click();
  await expect(page.getByRole('img', { name: '비공개 러닝 경로' })).toBeVisible();
  if (process.env.COACH_PREVIEW_DIR && test.info().project.name === 'desktop-chromium') {
    await page.getByRole('heading', { name: /러닝 분석/ }).scrollIntoViewIfNeeded();
    await page.screenshot({ path: path.join(process.env.COACH_PREVIEW_DIR, 'coach-upgrade-analysis.png') });
    await page.locator('.coach-report').screenshot({ path: path.join(process.env.COACH_PREVIEW_DIR, 'coach-upgrade-coach.png') });
  }
  await nav.getByRole('button', { name: '훈련 계획', exact: true }).click();
  await page.getByRole('button', { name: '이번 주 계획 생성' }).click();
  await page.getByRole('button', { name: '훈련 편집', exact: true }).first().click();
  await page.getByLabel('편집 훈련 종류').selectOption('interval');
  await page.getByLabel('인터벌 반복 거리').selectOption('800');
  await page.getByLabel('인터벌 반복 횟수').fill('4');
  await page.getByLabel('목표 기준').selectOption('pace');
  await page.getByLabel('목표 페이스 빠른 쪽').fill('4:55');
  await page.getByLabel('목표 페이스 느린 쪽').fill('5:10');
  await page.getByRole('button', { name: '훈련 저장' }).click();
  await expect(page.getByRole('dialog')).not.toBeVisible();
  await expect(page.getByRole('heading', { name: '거리 인터벌 5.8 km' })).toBeVisible();
  await expect(page.getByText('4′55″–5′10″ /km', { exact: true }).first()).toBeVisible();
  await page.getByRole('button', { name: '훈련 편집', exact: true }).first().click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.getByRole('dialog')).not.toBeVisible();
  await page.reload();
  await nav.getByRole('button', { name: '훈련 계획', exact: true }).click();
  await expect(page.getByRole('heading', { name: '거리 인터벌 5.8 km' })).toBeVisible();
  if (process.env.COACH_PREVIEW_DIR && test.info().project.name === 'desktop-chromium') {
    await page.getByRole('heading', { name: '거리 인터벌 5.8 km' }).scrollIntoViewIfNeeded();
    await page.screenshot({ path: path.join(process.env.COACH_PREVIEW_DIR, 'coach-upgrade-plan.png') });
  }
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});

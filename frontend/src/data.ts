import type { Store, User } from './types';
import { defaultPermissions } from './domain';
export const identityNames = ['Nguyễn Văn Tài', 'Nguyễn Văn Dương', 'Lưu Hoàng Phúc'];
export function createSeed(): Store {
  const userRoles: User['roles'][] = [
    ['Super Admin', 'Operator'],
    ['Admin', 'Researcher'],
    ['Researcher', 'Operator', 'Tester'],
  ];
  return {
    users: identityNames.map((name, i) => ({
      id: `USR-00${i + 1}`,
      name,
      email: ['tai', 'duong', 'phuc'][i] + '@robonose.local',
      department: 'RoboNose',
      title: 'Thành viên dự án',
      phone: '',
      roles: userRoles[i],
      status: 'Active',
      mfa: false,
      lastLogin: '—',
      group: i === 0 ? 'Nhóm vận hành' : 'Nhóm nghiên cứu',
    })),
    samples: [],
    people: identityNames.map((name, i) => ({
      id: `P00${i + 1}`,
      name,
      consent: false,
      note: 'Hồ sơ nhận diện mùi cơ thể. Trạng thái đồng ý cần được người vận hành xác nhận.',
    })),
    invitations: [],
    audits: [],
    results: [],
    models: [
      {
        id: 'MODEL-001',
        name: 'Odor Identity · Cosine',
        version: '1.0.0',
        channels: 'BME gas · MQ135 · MQ3 (legacy)',
        metrics: '10 đặc trưng · chưa đánh giá độc lập',
        active: false,
        date: '25/10/2026',
      },
      {
        id: 'MODEL-002',
        name: 'Body Odor Identity · UI Preview',
        version: '0.2.0-demo',
        channels: 'TGS2602 · MQ3 #1 · MQ135 #2 · MQ3 #2 · BME688',
        metrics: 'Giao diện nhận diện; chưa tích hợp suy luận AI',
        active: true,
        date: '17/11/2026',
      },
    ],
    permissions: defaultPermissions(),
    settings: {
      labName: 'RoboNose BioID',
      timezone: 'Asia/Ho_Chi_Minh',
      baseline: '60',
      exposure: '120',
      recovery: '60',
      sessionTimeout: '30',
      passwordLength: '12',
      auditRetention: '180',
      sampleRetention: '365',
      email: 'lab@robonose.local',
      language: 'Tiếng Việt',
      requireMfa: 'false',
      notifications: 'true',
    },
  };
}

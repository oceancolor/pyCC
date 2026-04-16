#!/usr/bin/env node
/**
 * 腾讯文档整点报告脚本
 * 每小时整点运行，对比快照报告文件变化
 *
 * 扫描范围：仅扫描"个人空间"（Benjamin 的工作相关文件）
 * 排除范围：由 PERSONAL_KEYWORDS 匹配到的个人/家庭文件不纳入工作报告
 *
 * 个人空间 space_id: RNpyegIMkEzt
 */

const { execSync } = require('child_process');
const fs = require('fs');
const path = require('path');

const SNAPSHOT_FILE = path.join(__dirname, 'tencent_docs_snapshot.json');

// 个人/家庭文件关键词 —— 匹配到的文件会被隔离，不出现在工作报告中
// 这些文件依然存在于你的腾讯文档，只是不被工作报告统计
const PERSONAL_KEYWORDS = [
  '班', '年级', '评优', '学期', '家长', '学考', '口算', '数学作业',
  '干部意向', '义工', '运动会服装', '入校面谈',
  '高中历史', '暑假作业', '暑假数学',
];

function isPersonalFile(title) {
  return PERSONAL_KEYWORDS.some(kw => title.includes(kw));
}

// 递归获取空间节点（处理分页）
async function getSpaceNodes(spaceId) {
  const nodes = [];
  let parentId = null; // null = 根目录

  async function fetchPage(pid) {
    const args = JSON.stringify({ space_id: spaceId, num: 100, ...(pid ? { parent_id: pid } : {}) });
    const result = execSync(
      `mcporter call tencent-docs query_space_node '${args}'`,
      { encoding: 'utf8', timeout: 30000 }
    );
    const data = JSON.parse(result);
    const children = data?.children || [];
    for (const node of children) {
      nodes.push(node);
      // 如果是文件夹，递归获取子节点
      if (node.node_type === 'wiki_folder' || node.type === 'folder') {
        await fetchPage(node.node_id || node.id);
      }
    }
  }

  await fetchPage(parentId);
  return nodes;
}

async function main() {
  const now = new Date();
  const timeStr = now.toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' });

  let allNodes;
  try {
    allNodes = await getSpaceNodes('RNpyegIMkEzt');
  } catch (e) {
    process.stdout.write(`[${timeStr}] ❌ 获取腾讯文档列表失败：${e.message}\n`);
    process.exit(1);
  }

  // 只保留文件节点（排除文件夹），且过滤掉个人/家庭文件
  const workFiles = allNodes.filter(n => {
    const isFolder = n.node_type === 'wiki_folder' || n.type === 'folder';
    if (isFolder) return false;
    const title = n.title || n.name || '';
    return !isPersonalFile(title);
  });

  const currentMap = {};
  for (const n of workFiles) {
    const id = n.node_id || n.id;
    if (id) {
      currentMap[id] = {
        id,
        title: n.title || n.name || '(无标题)',
        type: n.doc_type || n.type,
        modified: n.modified_time || n.update_time || null,
      };
    }
  }
  const currentTotal = Object.keys(currentMap).length;

  // 读取上次快照
  let prevMap = null;
  if (fs.existsSync(SNAPSHOT_FILE)) {
    try {
      prevMap = JSON.parse(fs.readFileSync(SNAPSHOT_FILE, 'utf8'));
    } catch (e) {
      prevMap = null;
    }
  }

  // 保存当前快照（仅工作文件）
  fs.writeFileSync(SNAPSHOT_FILE, JSON.stringify(currentMap, null, 2), 'utf8');

  let report;
  if (!prevMap) {
    report = `📄 腾讯文档整点报告 [${timeStr}]\n共 ${currentTotal} 个工作文件（首次统计，无对比基准）\n📌 扫描范围：个人空间（工作文件，已隔离个人/家庭文档）`;
  } else {
    const prevIds = new Set(Object.keys(prevMap));
    const currIds = new Set(Object.keys(currentMap));

    const added = [...currIds].filter(id => !prevIds.has(id));
    const deleted = [...prevIds].filter(id => !currIds.has(id));
    const modified = [...currIds].filter(id => {
      if (!prevIds.has(id)) return false;
      const prev = prevMap[id];
      const curr = currentMap[id];
      return curr.modified && prev.modified && curr.modified !== prev.modified;
    });

    report = `📄 腾讯文档整点报告 [${timeStr}]
共 ${currentTotal} 个工作文件
📥 新增：${added.length} 个${added.length > 0 ? '（' + added.map(id => currentMap[id].title).join('、') + '）' : ''}
🗑️ 删除：${deleted.length} 个${deleted.length > 0 ? '（' + deleted.map(id => prevMap[id].title).join('、') + '）' : ''}
✏️ 修改：${modified.length} 个${modified.length > 0 ? '（' + modified.map(id => currentMap[id].title).join('、') + '）' : ''}`;
  }

  process.stdout.write(report + '\n');
}

main();

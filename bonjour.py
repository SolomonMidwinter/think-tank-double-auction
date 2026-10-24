import random
import sys
from collections import Counter
import numpy as np



action_space=["R", "P", "S"]
BEATS = {"R": "S", "P": "R", "S": "P"}  # key 赢 value





def calculate_individual_influence(actions_i, actions_j, states):
    """
    计算玩家 i 对玩家 j 的个体影响力 gamma(i; j)
    公式参考论文 Equation (6)
    """
    total_t = len(states)
    state_counts = Counter(states)

    # 按照不同的状态分组记录动作对
    state_to_actions = {}
    for s, ai, aj in zip(states, actions_i, actions_j):
        if s not in state_to_actions:
            state_to_actions[s] = []
        state_to_actions[s].append((ai, aj))

    gamma = 0.0

    # 遍历每个出现的博弈状态
    for s, joint_actions in state_to_actions.items():
        p_s = state_counts[s] / total_t  # p(s)
        n_s = len(joint_actions)

        # 统计当前状态下的经验概率
        joint_counts = Counter(joint_actions)                     # N(ai, aj, s)
        i_counts = Counter([pair[0] for pair in joint_actions])   # N(ai, s)
        j_counts = Counter([pair[1] for pair in joint_actions])   # N(aj, s)

        sum_actions = 0.0
        for (ai, aj), c_ij in joint_counts.items():
            p_ij_given_s = c_ij / n_s          # p(ai, aj | s)
            p_i_given_s = i_counts[ai] / n_s   # p(ai | s)
            p_j_given_s = j_counts[aj] / n_s   # p(aj | s)

            # 计算条件互信息，避免 log(0)
            if p_ij_given_s > 0 and p_i_given_s > 0 and p_j_given_s > 0:
                # 论文中通常使用信息论的以 2 为底的对数 (bits)
                sum_actions += p_ij_given_s * np.log2(p_ij_given_s / (p_i_given_s * p_j_given_s))

        gamma += p_s * sum_actions

    return gamma

def calculate_net_influence(actions, states=None):
    """
    输入 {玩家名: 动作序列}，计算两两之间的 Net Influence（支持 N >= 3 个玩家）
    """
    players = list(actions)
    # 如果未提供状态序列，则默认游戏是无记忆的（所有回合处于同一个虚拟状态）
    if states is None:
        states = [0] * len(actions[players[0]])

    # 1. 计算所有玩家对之间的个体影响力 gamma(i; j)
    gamma = {}
    for i in players:
        for j in players:
            if i != j:
                gamma[(i, j)] = calculate_individual_influence(actions[i], actions[j], states)

    # 2. 计算网络影响力 Gamma(i; j) = gamma(i; j) - max_{k != i,j} gamma(k; j)
    net_influence = {}
    for i in players:
        for j in players:
            if i != j:
                strongest_other = max(gamma[(k, j)] for k in players if k != i and k != j)
                net_influence[(i, j)] = gamma[(i, j)] - strongest_other

    return gamma, net_influence

def detect_collusion(net_influence, threshold=0.05):
    """
    当且仅当 Γ(i;j) 和 Γ(j;i) 同时大于阈值时，判定 i 和 j 存在合谋
    """
    pairs = []
    for (i, j), val in net_influence.items():
        if i < j and val > threshold and net_influence[(j, i)] > threshold:
            pairs.append((i, j))
    return pairs

def permutation_null(actions, states, n_perm=200, seed=0):
    """
    置换检验：在每个状态内部打乱每个玩家的动作，破坏玩家之间的依赖，
    但保留每个玩家在每个状态下的动作分布。返回每对 (i, j) 的 Γ 零分布。
    """
    rng = random.Random(seed)
    players = list(actions)
    idx_by_state = {}
    for t, s in enumerate(states):
        idx_by_state.setdefault(s, []).append(t)

    null = {(i, j): [] for i in players for j in players if i != j}
    for _ in range(n_perm):
        shuffled = {}
        for p in players:
            seq = list(actions[p])
            for idx in idx_by_state.values():
                vals = [seq[t] for t in idx]
                rng.shuffle(vals)
                for t, v in zip(idx, vals):
                    seq[t] = v
            shuffled[p] = seq
        _, net = calculate_net_influence(shuffled, states)
        for pair, val in net.items():
            null[pair].append(val)
    return null


def reward(playerA, playerB, playerC):
    if playerA == playerB == playerC:
        return 0, 0, 0
    elif playerA != playerB and playerA != playerC and playerB != playerC:
        return 1,1,1
    else:
        return reward_matrix(playerA, playerB, playerC)

def reward_matrix(playerA, playerB, playerC):

    if playerB == playerC:
        ra,rb = reward1(playerA, playerB)
        return ra, rb, rb
    elif playerA == playerC:
        rb,ra = reward1(playerB, playerA)
        return ra, rb, ra
    elif playerA == playerB:
        rc,ra = reward1(playerC, playerA)
        return ra, ra, rc

def reward1(playerA, playerB):
    if playerA == "R" and playerB == "S" :
        return 1, 0
    elif playerA == "P" and playerB == "R":
        return 1, 0
    elif playerA == "S" and playerB == "P":
        return 1, 0
    elif playerA == "R" and playerB == "P":
        return 0, 1
    elif playerA == "P" and playerB == "S":
        return 0, 1
    elif playerA == "S" and playerB == "R":
        return 0, 1

def manual_collude(collusion_probability):
    """
    助手合谋：A 和 C 随机出拳；B 以 collusion_probability 的概率出 A 能赢的动作（故意输给 A），
    否则随机出拳。B 的合谋动作只取决于 A，不取决于 C。
    """
    playerA = random.choice(action_space)
    playerC = random.choice(action_space)
    if random.random() < collusion_probability:
        playerB = BEATS[playerA]
    else:
        playerB = random.choice(action_space)

    return playerA, playerB, playerC

def simulate(collusion_probability, num_games):
    actions_A,actions_B,actions_C=[],[],[]
    for i in range(num_games):
        a,b,c = manual_collude(collusion_probability)
        actions_A.append(a)
        actions_B.append(b)
        actions_C.append(c)
    actions = {'A': actions_A, 'B': actions_B, 'C': actions_C}

    # 在迭代马尔可夫博弈中，通常将“上一轮的联合动作”作为当前轮的状态 s
    # 这里我们构造一个简单的状态表达：上一轮三人的动作元组（第一轮用虚拟状态-1代替）
    states = [-1]
    for t in range(1, num_games):
        states.append((actions_A[t-1], actions_B[t-1], actions_C[t-1]))
    return actions, states

def sweep(cps=(0.0, 0.05, 0.1, 0.2, 0.4), game_counts=(100, 300, 1000, 3000), n_seeds=50, threshold=0.05):
    """
    准确率 = 恰好只检测出 (A, B) 这一对的比例；误报率 = CP=0 时检测出任意一对的比例
    """
    print(f"\n--- 3. 扫描 CP × 局数（每格 {n_seeds} 个随机种子，阈值 {threshold}）---")
    print("CP     " + "".join(f"n={n:<8d}" for n in game_counts))
    for cp in cps:
        row = []
        for n in game_counts:
            hits = 0
            for seed in range(n_seeds):
                random.seed(seed)
                actions, states = simulate(cp, n)
                _, net = calculate_net_influence(actions, states)
                found = detect_collusion(net, threshold)
                hits += (found == [('A', 'B')]) if cp > 0 else (len(found) > 0)
            row.append(hits / n_seeds)
        print(f"{cp:<7.2f}" + "".join(f"{r:<10.2f}" for r in row))


# =====================================================================
# 运行示例：模拟论文中的助手合谋（Assistant Collusion）场景
# 场景设定：A 和 C 随机出拳；B 是 A 的合谋助手，有 40% 的概率故意输给 A
# 运行 `python bonjour.py --sweep` 额外输出 CP × 局数 的准确率表
# =====================================================================
if __name__ == "__main__":
    random.seed(42)  # 固定随机种子（动作由 random 模块生成）
    num_games = 1000
    collusion_probability = 0.4  # 合谋概率 (CP = 0.4)

    actions, states = simulate(collusion_probability, num_games)

    # 计算影响力
    gamma_dict, net_inf_dict = calculate_net_influence(actions, states)
    null = permutation_null(actions, states)

    print("--- 1. 个体影响力 (Individual Influence γ) ---")
    for pair, val in gamma_dict.items():
        print(f"γ({pair[0]} -> {pair[1]}): {val:.4f}")

    print("\n--- 2. 网络影响力 (Net Influence Γ) ---")
    print("注：当且仅当 Γ(i;j) 和 Γ(j;i) 同时大于阈值(如0.05)时，判定 i 和 j 存在合谋。")
    print("p 值来自置换检验：零分布中 Γ 不小于观测值的比例。")
    for pair, val in net_inf_dict.items():
        p_value = (1 + sum(v >= val for v in null[pair])) / (1 + len(null[pair]))
        # 用加粗或高亮标记显著的合谋特征
        marker = " ★ [检测到强相关]" if val > 0.05 else ""
        print(f"Γ({pair[0]} -> {pair[1]}): {val:.4f}  p={p_value:.3f}{marker}")
    print(f"\n检测结果：{detect_collusion(net_inf_dict) or '无'}")

    if "--sweep" in sys.argv:
        sweep()

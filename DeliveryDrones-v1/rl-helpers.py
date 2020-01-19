from collections import defaultdict, Counter
import matplotlib.pyplot as plt
import seaborn as sns
from tqdm import tqdm_notebook
import pandas as pd
import numpy as np
import random
import torch
import torch.nn as nn
import torch.optim as optim
from torch import Tensor, LongTensor
import gym.spaces as spaces
import random
from collections import deque

def set_seed(env, seed):
    """Helper function to set the seeds when needed"""
    env.seed(seed) # Environment seed
    env.action_space.seed(seed) # Seed for env.action_space.sample()
    np.random.seed(seed) # Numpy seed
    torch.manual_seed(seed)  # PyTorch seed
    random.seed(seed) # seed for Python random library

class MultiAgentTrainer():
    """A class to train agents in a multi-agent environment"""
    def __init__(self, env, agents, seed=None):
        # Save parameters
        self.env, self.agents, self.seed = env, agents, seed
        
        # Create log of rewards and reset agents
        self.rewards_log = {key: [] for key in self.agents.keys()}
        self.reset()
        
    def reset(self):
        # Set seed for reproducibility
        if self.seed is not None:
            set_seed(self.env, self.seed)
        
        # Reset agents and clear log of rewards
        for key, agent in self.agents.items():
            agent.reset()
            self.rewards_log[key].clear()

    def train(self, n_steps):
        # Reset env. and get initial observations
        states = self.env.reset()
        
        for i in tqdm_notebook(range(n_steps), 'Training agents'):
            # Select actions based on current states
            actions = {key: agent.act(states[key]) for key, agent in self.agents.items()}

            # Perform the selected action
            next_states, rewards, dones, _ = self.env.step(actions)

            # Learn from experience
            for key, agent in self.agents.items():
                agent.learn(states[key], actions[key], rewards[key], next_states[key], dones[key])
                self.rewards_log[key].append(rewards[key])
            states = next_states
    
def test_agents(env, agents, n_steps, seed=None):
    """Function to test agents"""
    
    # Initialization
    if seed is not None:
        set_seed(env, seed=seed)
    states = env.reset()
    rewards_log = defaultdict(list)
    
    for _ in tqdm_notebook(range(n_steps), 'Testing agents'):
        # Select actions based on current states
        actions = {key: agent.act(states[key]) for key, agent in agents.items()}
        
        # Perform the selected action
        next_states, rewards, dones, _ = env.step(actions)
        
        # Save rewards
        for key, reward in rewards.items():
            rewards_log[key].append(reward)
        
        states = next_states

    return rewards_log

def plot_cumulative_rewards(rewards_log, ax=None, subset=None):
    # Creat figure etc.. if ax none
    create_figure = (ax is None)
    if create_figure:
        fig = plt.figure(figsize=(12, 4))
        ax = fig.gca()
        
    # Define which entry to plot
    subset = rewards_log.keys() if subset is None else subset
    
    # Plot rewards
    for key, rewards in rewards_log.items():
        if key in subset:
            # Work with Numpy array
            rewards = np.array(rewards)
            pickup = (rewards == 1)
            crashed = (rewards == -1) | (rewards == -2)

            # Compute cumulative sum
            cumsum = np.cumsum(rewards)
            idxs = range(1, len(cumsum) + 1)

            # Create label with pickup/crash rate
            label = r'Drone {} - reward: {:.3f}±{:.3f}, pickup: {:.2f}% ({}) crash: {:.2f}% ({})'.format(
                key, np.mean(rewards), np.std(rewards),
                100*pickup.mean(), pickup.sum(), 100*crashed.mean(), crashed.sum())

            # Plot results
            ax.step(idxs, cumsum, label=label)

    ax.set_xlabel('Step')
    ax.set_ylabel('Cumulative reward')
    ax.legend()
    
    if create_figure:
        plt.show()
    
def plot_rolling_rewards(rewards_log, ax=None, window=None, hline=None, subset=None):
    # Creat figure etc.. if ax none
    create_figure = (ax is None)
    if create_figure:
        fig = plt.figure(figsize=(12, 4))
        ax = fig.gca()
        
    # Define which entry to plot
    subset = rewards_log.keys() if subset is None else subset
        
    for key, rewards in rewards_log.items():
        if key in subset:
            # Work with Numpy array
            rewards = np.array(rewards)
            steps = range(1, len(rewards)+1)
            pickup = (rewards == 1)
            crashed = (rewards == -1) | (rewards == -2)

            # Set default for window size
            window = int(len(rewards)/10) if window is None else window

            # Plot rolling mean
            rolling_mean = pd.Series(rewards).rolling(window).mean()
            label = 'Drone {} - pickup: {} crash: {}'.format(key, pickup.sum(), crashed.sum())
            ax.plot(steps, rolling_mean,label=label)
        
    if hline is not None:
        ax.axhline(hline, label='target value', c='C0', linestyle='--')

    # Add title, labels and legend
    ax.set_xlabel('Steps (rolling window: {})'.format(window))
    ax.set_ylabel('Rewards')
    ax.legend()
    
    if create_figure:
        plt.show()
        
# Below are implementations of some standard RL agents
class RandomAgent():
    """Random agent"""
    def __init__(self, env):
        self.env = env
        
    def act(self, state):
        return self.env.action_space.sample()
    
    def reset(self):
        pass
    
    def learn(self, state, action, reward, next_state, done):
        pass
        
class QLearningAgent():
    """
    A Q-learning implementation that uses a dictionary as table
    with flattened observations as keys leveraging gym.spaces.flatten()
    Note: The action space has to be a gym.space.Discrete() object
    """
    def __init__(self, env, gamma, alpha, epsilon_start, epsilon_decay, epsilon_end):
        # Sanity checks related to this particular implementation
        isinstance(env.action_space, spaces.Discrete)
        isinstance(env.observation_space, spaces.Space)
        
        self.env = env
        self.gamma = gamma # Discount factor
        self.alpha = alpha # Learning rate
        self.epsilon_start = epsilon_start # Exploration rate
        self.epsilon_decay = epsilon_decay # Decay after each episode
        self.epsilon_end = epsilon_end # Minimum value
        self.is_greedy = False # Does the agent behave greedily?
        
    def reset(self):
        # Reset Q-table, exploration rate (before training)
        self.q_table = {}
        self.epsilon = self.epsilon_start
        self.epsilons = [] # Log of epsilon values

    def learn(self, state, action, reward, next_state, done):
        # Compute td-target
        if done:
            td_target = reward # Ignore future return
        else:
            td_target = reward + self.gamma * max(self.get_qvalues(next_state))
            
        # Epsilon decay
        if done:
            self.epsilons.append(self.epsilon)
            self.epsilon = max(self.epsilon * self.epsilon_decay, self.epsilon_end)
        
        # Update Q-table using the TD target and learning rate
        new_qvalue = (1 - self.alpha) * self.get_qvalues(state)[action] + self.alpha * td_target
        self.get_qvalues(state)[action] = new_qvalue

    def act(self, state):
        # Exploration rate
        epsilon = 0.01 if self.is_greedy else self.epsilon
            
        if np.random.rand() < epsilon:
            return self.env.action_space.sample()
        else:
            return np.argmax(self.get_qvalues(state)) # Greedy action
    
    def get_qvalues(self, state):
        # Flatten state
        state = tuple(spaces.flatten(self.env.observation_space, state))
        
        # Generate new entry in table for new states
        if state not in self.q_table:
            self.q_table[state] = np.random.rand(self.env.action_space.n)
            
        return self.q_table[state]
    
    def get_qtable(self, values_fmt='{:.2g}'):
        # Format states
        if hasattr(self.env, 'format_state'):
            unflatten_f = lambda x: spaces.unflatten(self.env.observation_space, x)
            states = map(self.env.format_state, map(unflatten_f, self.q_table.keys()))
        else:
            states = ['state {}'.format(i) for i in range(len(self.q_table))]
            
        # Format actions
        actions = map(self.env.format_action, range(self.env.action_space.n))
        
        # Create, format and render DataFrame
        df = pd.DataFrame(self.q_table.values(), list(states), list(actions))
        df = df.applymap(values_fmt.format)
        
        return df
    
class DenseQNetwork(nn.Module):
    """
    A 2-layer dense Q-network for OpenAI Gym spaces input/outputs
    """
    def __init__(self, env, hidden_size):
        # Initialize module
        super().__init__()
        self.env = env
        
        # Define network
        self.input_size = spaces.flatdim(self.env.observation_space)
        self.hidden_size = hidden_size
        self.output_size = self.env.action_space.n
        self.network = nn.Sequential(
            nn.Linear(self.input_size, self.hidden_size),
            nn.ReLU(),
            nn.Linear(self.hidden_size, self.output_size))
        
        # Move network to GPU if available
        if torch.cuda.is_available():
            self.network.cuda()
        
    def forward(self, states):
        # Forward flattened state
        states_flattened = [spaces.flatten(self.env.observation_space, s) for s in states]
        states_tensor = Tensor(states_flattened)

        # Move tensor to GPU if available
        if torch.cuda.is_available():
            states_tensor.cuda()
            
        return self.network(states_tensor)
            
class DQNAgent():
    """
    Deep Q-network agent (DQN) implementation
    Uses a NN to approximate the Q-function, a replay memory buffer
    and a target network.
    """
    def __init__(self, env, gamma, epsilon_start, epsilon_decay, epsilon_end, memory_size, batch_size, target_update_interval):
        # Action space and observation spaces should by OpenAI gym spaces
        isinstance(env.action_space, spaces.Discrete)
        isinstance(env.observation_space, spaces.Space)
        
        # Save parameters
        self.env = env
        self.gamma = gamma # Discount factor
        self.epsilon_start = epsilon_start # Exploration rate
        self.epsilon_decay = epsilon_decay # Decay after each episode
        self.epsilon_end = epsilon_end # Minimum value
        self.memory_size = memory_size # Size of the replay buffer
        self.batch_size = batch_size # Batch size
        self.target_update_interval = target_update_interval # Update rate
        self.is_greedy = False # Does the agent behave greedily?

    def reset(self):
        # Create networks with episode counter to know when to update them
        self.network, self.optimizer = self.create_qnetwork()
        self.target_network, _ = self.create_qnetwork()
        self.num_episode = 0
        
        # Reset exploration rate
        self.epsilon = self.epsilon_start
        self.epsilons = []
        
        # Create new replay memory
        self.memory = deque(maxlen=self.memory_size)
        
    def create_qnetwork(self):
        # Create network and optimizer
        network = DenseQNetwork(self.env, hidden_size=128)
        optimizer = optim.Adam(network.parameters())
        return network, optimizer
    
    def act(self, state):
        # Exploration rate
        epsilon = 0.01 if self.is_greedy else self.epsilon
        
        if np.random.rand() < epsilon:
            return self.env.action_space.sample()
        else:
            q_values = self.network([state])[0]
            return q_values.argmax().item() # Greedy action

    def learn(self, state, action, reward, next_state, done):
        # Memorize experience
        self.memory.append((state, action, reward, next_state, done))
        
        # End of episode
        if done: 
            self.num_episode += 1 # Episode counter
            self.epsilons.append(self.epsilon) # Log epsilon value
            
            # Epislone decay
            self.epsilon = max(self.epsilon * self.epsilon_decay, self.epsilon_end)
            
        # Periodically update target network with current one
        if self.num_episode % self.target_update_interval == 0:
            self.target_network.load_state_dict(self.network.state_dict())

        # Train when we have enough experiences in the replay memory
        if len(self.memory) > self.batch_size:
            # Sample batch of experience
            batch = random.sample(self.memory, self.batch_size)
            state, action, reward, next_state, done = zip(*batch)

            # Q-value for current state given current action
            q_values = self.network(state)
            q_value = q_values.gather(1, LongTensor(action).unsqueeze(1)).squeeze(1)

            # Compute the TD target
            next_q_values = self.target_network(next_state)
            next_q_value = next_q_values.max(1)[0]
            td_target = Tensor(reward) + self.gamma * next_q_value * (1 - Tensor(done))

            # Optimize quadratic loss
            loss = (q_value - td_target.detach()).pow(2).mean()
            self.optimizer.zero_grad()
            loss.backward()
            self.optimizer.step()
        
class MyDQNAgent(DQNAgent):
    """DQN Agent with custom Q-network"""
    def __init__(self, *args, conv_sizes=[32, 64, 64], fc_sizes=[128], **kwargs):
        # Initialize agent
        super().__init__(*args, **kwargs)
        
        # Save other parameters
        self.conv_sizes = conv_sizes
        self.fc_sizes = fc_sizes
        
    def create_qnetwork(self):
        # Create network
        network = MyQNetwork(self.env, self.conv_sizes, self.fc_sizes)

        # Move to GPU if available
        if torch.cuda.is_available():
            network.cuda()

        # Create optimizer
        optimizer = optim.Adam(network.parameters())
        
        return network, optimizer
    
class MyQNetwork(nn.Module):
    def __init__(self, env, conv_sizes, fc_sizes):
        # Initialize module
        super().__init__()
        
        # Get input size
        grisize, grisize, depth = env.observation_space.shape

        # Create convolutional layers
        self.conv = nn.Sequential()
        for i, kernels in enumerate(conv_sizes):
            # Create layer
            in_channels = depth if i == 0 else conv_sizes[i-1]
            out_channels = conv_sizes[i]
            layer = nn.Conv2d(in_channels, out_channels, kernel_size=3, stride=1, padding=1)

            # Add layer + activation
            self.conv.add_module('conv2d_{}'.format(i+1), layer)
            self.conv.add_module('ReLU_{}'.format(i+1), nn.ReLU())

        # Add classification layer
        self.fc = nn.Sequential()
        self.fc.add_module('flatten', nn.Flatten())

        conv_output = self.conv(torch.ones([1, depth, grisize, grisize]))
        batch_size, flatsize  = self.fc(conv_output).shape
        fc_sizes = fc_sizes + [env.action_space.n]
        for i, hidden_size in enumerate(fc_sizes):
            # Create layer
            in_features = flatsize if i == 0 else fc_sizes[i-1]
            out_features = fc_sizes[i]
            layer = nn.Linear(in_features, out_features)
                
            # Add layer + activation
            if i > 0:
                self.fc.add_module('ReLU_{}'.format(i+1), nn.ReLU())
            self.fc.add_module('fc_{}'.format(i+1), layer)
        
        self.network = nn.Sequential(self.conv, self.fc)
        
    def forward(self, states):
        # Forward flattened state
        batch_states = np.array(states).transpose(0, 3, 1, 2)
        return self.network(Tensor(batch_states))

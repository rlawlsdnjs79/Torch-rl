import torch
import numpy as np
from common.memory import ReplayMemory
from agent.core import Agent
from copy import deepcopy
from torch.optim import Adam
from torch import nn
import torch.nn.functional as F
from common.loss import huber_loss
from torch.autograd import Variable

class DDPG_Agent(Agent):
    def __init__(self, env, actor_model, critic_model, policy,
                 actor_lr=1e-3, critic_lr=1e-3,
                 actor_target_network_update_freq=1000, critic_target_network_update_freq=1000,
                 actor_training_freq=1, critic_training_freq=1,
                 ## hyper-parameter
                 gamma=0.90, batch_size=32, buffer_size=50000, learning_starts=1000,
                 target_network_update_freq=1000,
                 ## decay
                 decay=False, decay_rate=0.9,
                 ## prioritized_replay
                 prioritized_replay=False,
                 prioritized_replay_alpha=0.6, prioritized_replay_beta0=0.4, prioritized_replay_beta_iters=None,
                 prioritized_replay_eps=1e-6, param_noise=False,
                 ##
                 path=None):

        self.env = env
        self.policy = policy

        self.gamma = gamma
        self.batch_size = batch_size
        self.learning_starts = learning_starts

        self.actor_training_freq, self.critic_training_freq = actor_training_freq, critic_training_freq
        self.actor_target_network_update_freq = actor_target_network_update_freq
        self.critic_target_network_update_freq = critic_target_network_update_freq
        self.actor = actor_model
        self.critic = critic_model
        self.target_actor = deepcopy(actor_model)
        self.target_critic = deepcopy(critic_model)

        actor_optim = Adam(self.actor.parameters(), lr=actor_lr)
        critic_optim = Adam(self.critic.parameters(), lr=critic_lr)
        if decay:
            self.actor_optim = torch.optim.lr_scheduler.ExponentialLR(actor_optim, decay_rate, last_epoch=-1)
            self.critic_optim = torch.optim.lr_scheduler.ExponentialLR(critic_optim, decay_rate, last_epoch=-1)
        else:
            self.actor_optim = actor_optim
            self.critic_optim = critic_optim

        torch.nn.utils.clip_grad_norm_(self.actor.parameters(), 1, norm_type=2)
        torch.nn.utils.clip_grad_norm_(self.critic.parameters(), 1, norm_type=2)
        super(DDPG_Agent, self).__init__(path)
        example_input = Variable(torch.rand(100, self.env.observation_space.shape[0]))
        self.writer.add_graph(self.actor, input_to_model=example_input)
        example_input = Variable(torch.rand(100, self.env.observation_space.shape[0]+env.action_space.shape[0]))
        self.writer.add_graph(self.critic, input_to_model=example_input)


    def forward(self, observation):
        observation = observation.astype(np.float32)
        observation = torch.from_numpy(observation)
        action = self.actor.forward(observation)
        Q = self.critic(torch.stack([observation, action]), -1)
        action = action.data.numpy()
        return action, Q.detach().numpy()

    def backward(self, sample_):
        self.replay_buffer.push(sample_)
        if self.step > self.learning_starts and self.learning:
            sample = self.replay_buffer.sample(self.batch_size)
            assert len(sample["s"]) == self.batch_size
            a = sample["a"].long().unsqueeze(1)
            "update the critic "
            if self.step % self.critic_training_freq == 0:
                input = torch.stack(sample["s"], sample["a"])
                Q = self.critic(sample["s"], sample["a"])
                target_a = self.target_actor(sample["s_"])
                target_input = torch.stack()
                targetQ = self.target_critic(sample["s_"], target_a)
                targetQ = targetQ.squeeze(1)
                Q = Q.squeeze(1)
                expected_q_values = sample["r"] + self.gamma * targetQ * (1.0 - sample["tr"])
                loss = torch.mean(huber_loss(expected_q_values - Q))
                self.critic.zero_grad()
                loss.backward()
                self.critic_optim.step()
            "training the actor"
            if self.step % self.actor_training_freq == 0:
                action = self.actor(sample["s"])
                Q = self.critic(sample["s"],action)
                self.actor.zero_grad()
                Q.backward()
                self.actor_optim.step()
            if self.step % self.actor_target_network_update_freq == 0:
                self.target_actor_net_update()
            if self.step % self.critic_target_network_update_freq == 0:
                self.target_critic_net_update()

    def target_actor_net_update(self):
        self.target_actor.load_state_dict(self.actor.state_dict())

    def target_critic_net_update(self):
        self.target_critic.load_state_dict(self.critic.state_dict())

    def load_weights(self, filepath):
        model = torch.load(filepath)
        self.Q_net.load_state_dict(model["Q_net"])
        self.target_Q_net.load_state_dict(model["target_Q_net"])
        self.optim.load_state_dict(model["optim"])

    def save_weights(self, filepath, overwrite=False):
        torch.save({"Q_net": self.Q_net,
                    "target_Q_net": self.target_Q_net,
                    "optim": self.optim
                    }, filepath + "DQN.pkl")




import keyboard  
import cv2
import time
import numpy as np
from copy import deepcopy
from scipy.spatial import KDTree
import matplotlib.pyplot as plt
from EKF_SLAM import EKF_SLAM
from graph_SLAM import Graph_SLAM
plt.figure()

def angle_wrapping(theta):
    return deepcopy(np.arctan2(np.sin(theta), np.cos(theta)))

def visualize(world,plot_resolution):
    def draw_robot(image, world, pose, radius, color, alpha):
        start_point=(int((pose[0]+world.origin[0])*plot_resolution),int((pose[1]+world.origin[1])*plot_resolution))
        end_point=(int(start_point[0]+40*np.cos(pose[2])), int(start_point[1]+40*np.sin(pose[2])))
        image = cv2.arrowedLine(image, start_point, end_point,
                                         (0, 0, 0), 2)
        tem = deepcopy(image)
        tem= cv2.circle(tem, start_point, int(radius*plot_resolution),color, -1)
        image=cv2.addWeighted(image, 1-alpha, tem, alpha, 0)
        return image
    
    def draw_uncertainty(image, loc, covariance):
        loc=(loc+world.origin[0])*plot_resolution
        u, s, vh =np.linalg.svd(covariance)
        angle=np.arctan2(u[0,1], u[0,0])
        axes=np.sqrt(s)*plot_resolution
        image = cv2.ellipse(img=image, center=(int(loc[0]), int(loc[1])) ,axes=(int(axes[0]),int(axes[1])) ,
           angle=angle*180/np.pi, startAngle=0, endAngle=360, color=(255,255,0), thickness=2)
        return image 
    
    def draw_graph(image, graph):
        if len(graph.edges):
            thickness=[np.log(np.linalg.det(edge.omega)+1) for edge in graph.edges]
            thickness_range=np.max(thickness)-np.min(thickness)
            thickness=thickness/thickness_range*4
            thickness=thickness+1-np.min(thickness)
            thickness=np.clip(thickness, 1,5)
        for i,edge in enumerate(graph.edges):
            start_point=(edge.node1.x[0:2]+world.origin)*plot_resolution
            end_point=(edge.node2.x[0:2]+world.origin)*plot_resolution
            print(thickness[i])
            if edge.type=="odom":
                color=(255, 0, 0)
            elif edge.type=="measurement":
                color=(0, 255, 255)    
            else:
                color=(0, 0, 255)    
            image=cv2.line(image, (int(start_point[0]),int(start_point[1]) ), (int(end_point[0]),int(end_point[1]) ),color, int((thickness[i])))
            
        for node in graph.nodes:
            x=(node.x[0:2]+world.origin)*plot_resolution
            if node.type=="pose":
                color=(0,0,255)
            else:
                color=(0,255,255)
            image=cv2.circle(image, (int(x[0]),int(x[1])) , int(0.05*plot_resolution),color, 2)
        return image
    
    image=deepcopy(world.bkg_map)
    w=int(image.shape[0]*plot_resolution*world.map_resolution)
    h=int(image.shape[1]*plot_resolution*world.map_resolution)
    image= cv2.resize(image, (w,h), interpolation=cv2.INTER_NEAREST)
    if world.robot.slam.__class__.__name__=="Graph_SLAM":
        image=draw_graph(image, world.robot.slam.front_end)

    image=draw_robot(image,world, world.robot.x, world.robot.radius,  (131,46,75), 0.1)
    image=draw_robot(image,world, world.robot.odom, world.robot.radius, (131,46,75), 1)
    
    if world.robot.slam.__class__.__name__=="EKF_SLAM":
        image=draw_uncertainty(image, world.robot.odom[0:2], world.robot.covariance[0:2, 0:2] )
        for i in range(int((len(world.robot.odom)-3)/2)):
            loc=(world.robot.odom[2*i+3:2*i+5]+np.asarray(world.origin))*plot_resolution
            image= cv2.circle(image, (int(loc[0]),int(loc[1])), 2, (0,0,255), -1)
            image=draw_uncertainty(image, world.robot.odom[2*i+3:2*i+5], world.robot.covariance[2*i+3:2*i+5, 2*i+3:2*i+5])
        
    cv2.imshow('test', cv2.flip(image, 0))



def read_input(robot):
    if keyboard.is_pressed("w"):
        robot.tele_inputs(np.asarray([0.05,0]))
    if keyboard.is_pressed("x"):
        robot.tele_inputs(np.asarray([-0.05,0]))
    if keyboard.is_pressed("a"):
        robot.tele_inputs(np.asarray([0,0.05]))
    if keyboard.is_pressed("d"):
        robot.tele_inputs(np.asarray([0,-0.05]))
    if keyboard.is_pressed("s"):
        robot.stop()
def rotational_matrix(theta):
    return np.asarray([[np.cos(theta), np.sin(theta)],
                       [-np.sin(theta), np.cos(theta)]])

class World:
    def __init__(self, bkg_map, origin, map_resolution, agents):
        self.t=0
        self.bkg_map=bkg_map
        self.map_resolution=map_resolution        
        self.origin=origin
        self.bound=np.asarray([[-origin[0], map_resolution*bkg_map.shape[0]-origin[0]],
                               [-origin[1], map_resolution*bkg_map.shape[1]-origin[1]]])
        grayImage = cv2.cvtColor(map_img, cv2.COLOR_BGR2GRAY)
        _, blackAndWhiteImage = cv2.threshold(grayImage, 127, 255, cv2.THRESH_BINARY)
        obs_loc=np.where(blackAndWhiteImage==0)
        self.obstacles=[]
        obst_loc=[]
        for i, idx in enumerate(obs_loc[0]):
            obst_loc.append(np.asarray(([(obs_loc[1][i]+0.5)*map_resolution-origin[0],(obs_loc[0][i]+0.5)*map_resolution-origin[1]])))
            self.obstacles.append(Obstacle(obst_loc[-1], obs_id=i, is_feature=(np.random.uniform(0,1)<0.2)))
        self.robot=agents[0]
        self.robot.world=self
        self.obstacles_tree=KDTree(obst_loc)
        
    def collision_check(self):
        dists, idx=self.obstacles_tree.query(self.robot.x[0:2],5)
        for i,dist in enumerate(dists):
            if dist<=(self.robot.radius+self.map_resolution*0.5):
                print("colision")
                if not dist==0:
                    collision=1/dist*np.asarray([self.obstacles[idx[i]].loc[0]-self.robot.x[0], self.obstacles[idx[i]].loc[1]-self.robot.x[1]])
                    if np.dot(self.robot.x[3:5], collision)>=0:                        
                        self.robot.x[3:5]=self.robot.x[3:5]-np.dot(self.robot.x[3:5], collision)*collision

       # print(dist)
    def step(self, dt):
        self.dt=dt
        self.robot.input_eval()
        self.collision_check()
        self.robot.step(dt)
        self.t+=dt

class Obstacle:
    def __init__(self, loc, obs_id,is_feature):
        self.loc=loc
        self.id=obs_id
        self.is_feature=is_feature

class Camera:
    def __init__(self, robot, fov, depth,  range_noise, bearing_noise):
        self.fov=fov
        self.depth=depth         
        self.robot=robot 
        self.bearing_noise=bearing_noise
        self.range_noise=range_noise
        
    def measure(self):
        x=self.robot.x
        world=self.robot.world
        idx=self.robot.world.obstacles_tree.query_ball_point(x[0:2],self.depth)
        z=[[np.linalg.norm(world.obstacles[i].loc-x[0:2], 2), 
              angle_wrapping(np.arctan2(world.obstacles[i].loc[1]-x[1],world.obstacles[i].loc[0]-x[0])-x[2]),
              world.obstacles[i].id] for i in idx ]   
        
        z=[obs for obs in z if abs(obs[1])<=self.fov/2]  
        z=[[abs(np.random.normal(obs[0], self.range_noise)), angle_wrapping(np.random.normal(obs[1], self.bearing_noise)), obs[2] ]for obs in z]
        return z

    
class Robot:
    def __init__(self, input_noise, slam_method="EKF_SLAM"):
        self.camera=Camera(self, 87*np.pi/180, 2, 0.1,0.1)
        self.x=np.zeros(6)
        self.x[2]=np.pi/2
        self.radius=0.3
        self.u=np.zeros(2)
        self.feature=[]
        self.input_noise=input_noise
        measurement_noise=[self.camera.range_noise, self.camera.bearing_noise]
        self.x_est=[[0,0]]
        self.odom=deepcopy(self.x[0:3])
        if slam_method=="EKF_SLAM":
            self.slam=EKF_SLAM(deepcopy(self.x[0:3]),np.diag(input_noise)**2, np.diag(measurement_noise)**2)
        else:
            self.slam=Graph_SLAM(deepcopy(self.x[0:3]),np.diag(input_noise)**2, np.diag(measurement_noise)**2,STM_length=3)
        self.covariance=np.zeros(6)
        self.camera_rate=0.03

    def tele_inputs(self, u):
        self.u[0]+=u[0]
        self.u[1]+=u[1]
        self.u[0]=np.clip(self.u[0], -1,1)
        self.u[1]=np.clip(self.u[1], -1,1)

    def stop(self):
        self.u=np.zeros(2)

    def input_eval(self):
        trans=np.random.normal(self.u[0], self.input_noise[0])
        rot=np.random.normal(self.u[1], self.input_noise[1])
        if rot>=0.01:
            self.x[3]=1/dt*(-trans/rot*np.sin(self.x[2])+trans/rot*np.sin(self.x[2]+rot*dt))
            self.x[4]=1/dt*(trans/rot*np.cos(self.x[2])-trans/rot*np.cos(self.x[2]+rot*dt))
        else:
            self.x[3]=trans*np.cos(self.x[2]+1/2*self.world.dt*rot)
            self.x[4]=trans*np.sin(self.x[2]+1/2*self.world.dt*rot)
        
        self.x[5]=rot
        
    def observation(self, dt):
        obs=self.camera.measure()
        for i,z in enumerate(obs):
            z.append(self.world.obstacles[int(z[2])].is_feature)
        return obs
    
    def step(self, dt):
        z=self.observation(dt)
        x=self.x
        dx=np.asarray([dt*x[3],
                       dt*x[4],
                       dt*x[5],0,0,0])
        self.x+=dx
        self.x[2]=angle_wrapping(self.x[2])
        

        self.x[0]=np.clip(x[0], self.world.bound[0,0],self.world.bound[0,1])
        self.x[1]=np.clip(x[1], self.world.bound[1,0],self.world.bound[1,1])
        self.odom, self.covariance=self.slam.update(dt,z,deepcopy(self.u))
        

#%%
map_img = cv2.flip(cv2.imread("map.png"),0)
map_resolution=0.12 #meter/pixel
origin=[0.6,0.6]

robots=[Robot([0.05,0.1], slam_method="Graph_SLAM")]
world=World(map_img, origin, map_resolution, robots)
dt=0.01
#%%
loop=True
while loop:  # making a loop
  #  try:
        read_input(world.robot)
        world.step(dt)
        print("trans ", world.robot.u[0], "rot ", world.robot.u[1])
        visualize(world,plot_resolution=100) #pixel per meter
        if keyboard.is_pressed("esc"):  # if key 'q' is pressed 
             print('exit')
             loop=False 
        cv2.waitKey(1)
        time.sleep(dt)
        

  #  except Exception as e:
  #      print(e)
   #     cv2.destroyAllWindows()
   #     break
cv2.destroyAllWindows()

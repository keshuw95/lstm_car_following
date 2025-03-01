import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import torch
from torch import nn
from torch.utils.data import Dataset, DataLoader
import os
from model import LSTM_model


# 1. Data Loading
def load_data(data_path, len_d=100):
    """Loads and sorts traffic data from the specified directory."""
    files = os.listdir(data_path)
    files.sort()
    files = files[:len_d]
    print(f"Loaded {len(files)} files")
    return files


# 2. Data Preprocessing
def preprocess_data(files, input_time_dim=30, output_time_dim=50, n_leader=2, len_d=100):
    """Preprocesses data for training, including scaling and reshaping."""
    id_dict = {}
    x_l1_list = []
    v_l1_list = []
    x_l2_list = []
    v_l2_list = []
    x_f_list = []
    v_f_list = []
    a_f_list = []
    len_list = []

    split_line1 = 0
    split_line2 = 0

    M, n = input_time_dim, output_time_dim

    for i in range(len(files)):
        df = pd.read_csv('data/'+files[i], header=0)
        id_dict[i] = df['id'].values
        df = df.drop(['id'], axis=1)

        pos = df.values * 0.3048
        speed = (pos[:,1:] - pos[:,:-1])/0.1
        pos = pos[:,1:]

        acc = (speed[:,1:] - speed[:,:-1])/0.1
        speed = speed[:,1:]

        length = pos.shape[1]

        # plt.plot(pos[0,:])
        # plt.plot(pos[1,:])
        # plt.show()

        for j in range(M, length-n):
            x_l_j = pos[0, j-M:j+n]
            x_l1_list.append(x_l_j)

            v_l_j = speed[0, j-M:j+n]
            v_l1_list.append(v_l_j)

            x_l_j = pos[1, j-M:j+n]
            x_l2_list.append(x_l_j)

            v_l_j = speed[1, j-M:j+n]
            v_l2_list.append(v_l_j)

            x_f_j = pos[2, j-M:j+n]
            x_f_list.append(x_f_j)

            v_f_j = speed[2, j-M:j+n]
            v_f_list.append(v_f_j)

            a_f_j = acc[2, j-M:j+n]
            a_f_list.append(a_f_j)
        
        if i < int(0.6*len_d):
            split_line1 += length - n - M
        if i < int(0.8*len_d):
            split_line2 += length - n - M
        len_list.append(length - n - M)

    X_L1 = np.array(x_l1_list)
    V_L1 = np.array(v_l1_list)
    X_L2 = np.array(x_l2_list)
    V_L2 = np.array(v_l2_list)
    X_F = np.array(x_f_list)
    V_F = np.array(v_f_list)
    A_F = np.array(a_f_list)
        
    # print(X_L1.shape, V_L1.shape, X_L2.shape, V_L2.shape,X_F.shape, V_F.shape, A_F.shape, split_line1, split_line2)

    id_ = np.zeros((int(0.2*len_d),2), dtype=np.int64)
    for i in range(int(0.8*len_d), len_d):
        id_[i-int(0.8*len_d), 0] = i-int(0.8*len_d)+1
        id_[i-int(0.8*len_d), 1] = id_dict[i][-1]
        # print(i-int(0.8*len_d)+1, id_dict[i])
    id_df = pd.DataFrame(id_, columns=['Traj Num', 'vehicle ID'])
    os.makedirs('output', exist_ok=True)
    id_df.to_csv('output/vehicle_id.csv', index=False)

    # 3-vehcle platoon: L1-L2-F
    S1 = X_L1 - X_L2 # spacing between L1 and L2
    S2 = X_L2 - X_F # spacing between L2 and F
    V_d1 = V_L1 - V_L2 # speed difference between L1 and L2
    V_d2 = V_L2 - V_F # speed difference between L2 and F
    V1 = V_L1 # speed of L1
    V2 = V_L2 # speed of L2
    V3 = V_F # speed of F

    if n_leader == 2:
        C_in = np.stack([S1, S2, V_d1, V_d2, V1, V2, V3], axis=1)
        C_out = np.stack([X_L1, X_L2, X_F],axis=1)
        # C_out = np.stack([V_L1, V_L2, V_F],axis=1)
    else:
        C_in = np.stack([S2, V_d2, V2, V3], axis=1)
        C_out = np.stack([X_L2, X_F],axis=1)
        # C_out = np.stack([V_L2, V_F],axis=1)

    C_out = C_out - (np.ones(C_out.shape)*C_out[:,0:1,0:1])

    scale = np.max(C_out)
    C_out = (C_out)/scale

    # C_in = np.array(C_in, dtype=np.float32)
    # C_out = np.array(C_out, dtype=np.float32)

    X_train = C_in[:split_line1,:,:M]
    X_val = C_in[split_line1:split_line2,:,:M]
    X_test = C_in[split_line2:,:,:M]

    y_train = C_out[:split_line1,:,M:]
    y_val = C_out[split_line1:split_line2,:,M:]
    y_test = C_out[split_line2:,:,M:]


    X_train = torch.tensor(X_train, dtype=torch.float32)
    y_train = torch.tensor(y_train, dtype=torch.float32)

    X_val = torch.tensor(X_val, dtype=torch.float32)
    y_val = torch.tensor(y_val, dtype=torch.float32)

    X_test = torch.tensor(X_test, dtype=torch.float32)
    y_test = torch.tensor(y_test, dtype=torch.float32)

    # print(X_train.shape, y_train.shape, X_val.shape, y_val.shape, X_test.shape, y_test.shape)
    data = X_train, y_train, X_val, y_val, X_test, y_test, scale
    return data


# 3. Define Dataset Class
class MyDataset(Dataset):
    def __init__(self, x, y):
        super(MyDataset, self).__init__()
        assert x.shape[0] == y.shape[0]
        self.x = x
        self.y = y

    def __len__(self):
        return self.y.shape[0]

    def __getitem__(self, index):
        return self.x[index], self.y[index]
    

# Loss Calculation Function
def compute_loss(y_pred, batch_y, loss_fn, lambda_v, delta_t):
    """Computes the total loss including MSE and velocity consistency."""
    # Standard MSE Loss
    mse_loss = loss_fn(y_pred, batch_y)
    
    # Compute velocity
    v_pred = (y_pred[:, :, 1:] - y_pred[:, :, :-1]) / delta_t
    v_gt = (batch_y[:, :, 1:] - batch_y[:, :, :-1]) / delta_t

    # Velocity consistency loss (penalizing negative velocities)
    velocity_loss = torch.mean(torch.clamp(-v_pred, min=0) ** 2)
    
    
    # Total loss
    total_loss = mse_loss + lambda_v * velocity_loss
    
    return total_loss, mse_loss


# 4. Training Loop
def train_model(
    model, model_name, trainloader, valloader, epoch, l_r, scale, model_path, device, lambda_v=1.0, delta_t=0.1
):
    model = model.to(device)
    
    min_loss = 1e8
    loss_fn = torch.nn.MSELoss().to(device)

    optimiser = torch.optim.Adam((model.parameters()), lr=l_r)

    num_epochs = epoch

    train_hist = np.zeros(num_epochs)
    val_hist = np.zeros(num_epochs)


    for t in range(num_epochs):

        loss_epoch=[]
        loss_epoch_val=[]
        j = 0
        
        for batch_x, batch_y in trainloader:

            model.train()
            batch_x = batch_x.to(device)
            batch_y = batch_y.to(device)


            y_pred = model.forward(batch_x)
            total_loss, mse_loss = compute_loss(y_pred, batch_y, loss_fn, lambda_v, delta_t)
            
            total_loss.backward(retain_graph=True)
            loss_ = loss_fn(y_pred * scale, batch_y * scale)
            loss_epoch.append(loss_.item())
            
            optimiser.step()
            optimiser.zero_grad()
            
            if valloader is not None:
                with torch.no_grad():
                    
                    model.eval()

                    y_val_pred_list = []
                    y_val_true_list = []
                    for batch_x_val, batch_y_val in valloader:
                        batch_x_val = batch_x_val.to(device)
                        batch_y_val = batch_y_val.to(device)
                        
                        y_val_pred = model(batch_x_val)
                        total_val_loss, _ = compute_loss(y_val_pred, batch_y_val, loss_fn, lambda_v, delta_t)
                        
                        y_val_true_list.append(batch_y_val)
                        y_val_pred_list.append(y_val_pred)
                    Y_val_true = torch.cat(y_val_true_list)
                    Y_val_pred = torch.cat(y_val_pred_list)
                    val_loss = loss_fn(Y_val_pred.float(), Y_val_true)
                    val_loss_ = loss_fn(Y_val_pred.float()*scale, Y_val_true*scale)
                val_hist[t] = val_loss_.item()
                loss_epoch_val.append(val_loss_.item())
            
            if j % 10 == 0:
                print(f'Ep {t} - itr {j} | train loss: {loss_.item()}, validation loss: {val_loss_.item()}')
            j += 1

            if val_loss_.item() < min_loss:
                min_loss = val_loss_.item()
                torch.save(model, model_path)
                
        if valloader is not None:
            if t % 1 == 0:  
                print(f'Epoch {t} train loss: {np.mean(loss_epoch)}, validation loss: {np.mean(loss_epoch_val)}')
        else:
            if t % 1 == 0:
                print(f'Epoch {t} train loss: {np.mean(loss_epoch)}')
        train_hist[t] = np.mean(loss_epoch)

    print('best:', min_loss)

    return model.eval(), train_hist, val_hist


# 5. Evaluation
def evaluate_model(model_path, model_name, X_test, y_test, scale, device):
    """Evaluate the trained model."""
    model = torch.load(model_path, weights_only=False)
    model = model.to(device)
    model.eval()
    X_test = X_test.to(device)
    y_test = y_test.to(device)

    y_test_pred = model(X_test).cpu().detach().numpy()
    
    y_test_true = y_test.cpu().detach().numpy()

    rmse = np.sqrt(np.mean(np.square(y_test_pred*scale - y_test_true*scale)))
    print("Testing RMSE:", rmse)

    v_num = y_test_true.shape[1]
    labels = ['leader '+str(int(v+1)) for v in range(v_num-1)]
    labels.append('follower')
    linestyles = ['-', '--', '-.', ':']
    colors_gt = ['green' for v in range(v_num-1)]
    colors_gt.append('blue')
    colors_pred = ['orange' for v in range(v_num-1)]
    colors_pred.append('red')

    for i in range(1):
        fig = plt.figure(figsize=(8,5))
        for j in range(y_test_true.shape[1]):
            plt.plot(y_test_true[i,j,:]*scale, color=colors_gt[j], label='Ground Truth - '+labels[j], linestyle=linestyles[j])
            plt.plot(y_test_pred[i,j,:]*scale, color=colors_pred[j], label='Prediction - '+labels[j], linestyle=linestyles[j])
        plt.ylabel('Longitudial Position (m)')
        plt.xlabel('Time (0.1s)')
        plt.legend()
        plt.show()
        fig.savefig('output/eval_'+str(i)+'.png', dpi=300)
    return y_test_pred, y_test_true


# Main Function
def main():
    device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
    # device = torch.device("mps" if torch.cuda.is_available() else "cpu")
    
    input_time_dim, output_time_dim = 50, 80
    n_leader = 2

    model_name = 'LSTM'

    print("Preprocessing data...")
    # Dataset and DataLoader setup
    data_path = 'data' 
    files = load_data(data_path)
    X_train, y_train, X_val, y_val, X_test, y_test, scale = preprocess_data(files, input_time_dim=input_time_dim, output_time_dim=output_time_dim, len_d=100)
    
    traindata = MyDataset(X_train, y_train)
    valdata = MyDataset(X_val, y_val)
    trainloader = torch.utils.data.DataLoader(traindata, batch_size=512, shuffle=True)
    valloader = torch.utils.data.DataLoader(valdata, batch_size=512, shuffle=True)

    n_features = X_train.shape[1]
    print(X_train.shape)
    n_veh = y_train.shape[1]

    model = LSTM_model(n_features=n_features, n_hidden=256, n_veh=n_veh, n_out=output_time_dim, n_layers=2, device=device)
    
    epoch = 100
    l_r = 5e-4

    os.makedirs("model/CF_leader="+str(n_leader), exist_ok=True)
    model_path = 'model/CF_leader='+str(n_leader)+"/"+model_name+"_M=" + str(input_time_dim) + "_N=" + str(output_time_dim) + ".pt"

    print("Start training...")
    model, train_hist, test_hist = train_model(model, model_name, trainloader, valloader, epoch, l_r, scale, model_path, device)
    
    print("Start evaluation...")
    predictions, actuals = evaluate_model(model_path, model_name, X_test, y_test, scale, device)

if __name__ == "__main__":
    main()
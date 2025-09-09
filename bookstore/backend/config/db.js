import AWS from 'aws-sdk';


const connectDB = () => {

  AWS.config.getCredentials(function (err) {
    if (err) console.log(err.stack);
    // credentials not loaded
    else {
      console.log("Credentials successfully loaded".yellow);
    }
  });

  var credentials = new AWS.SharedIniFileCredentials({ profile: 'default' });
  AWS.config.credentials = credentials;

  AWS.config.update({
    region: process.env.REGION, // replace with your region in AWS account
    accessKeyId: AWS.config.credentials.accessKeyId,
    accessSecretKey: AWS.config.credentials.secretAccessKey,
    sessionToken: AWS.config.credentials.sessionToken,
  });

  console.log('BookStore is connected to Dynamo'.yellow)

}

export default connectDB